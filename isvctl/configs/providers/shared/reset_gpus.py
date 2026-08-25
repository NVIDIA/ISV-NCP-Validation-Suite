#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Reset GPUs on a node via SSH (BFX01-01).

Provider-agnostic SSH approach — mirrors the AHR GPU reset runbook sequence
that runs directly on the node rather than through a container runtime.
Works across bare metal, Kubernetes, and AWS without any container dependencies.

Provider wiring:
  Bare metal / AWS  →  --host HOST --ssh-user USER --ssh-key PATH
  Kubernetes        →  --machine-id NODE_NAME  (IP resolved via kubectl)

Reset sequence (executed on the node over SSH):
  1. Stop GPU services: Fabric Manager, IMEX, persistenced, DCGM, nvsm
  2. Unload nvidia kernel modules in dependency order
  3. sudo nvidia-smi -r
  4. Reload nvidia kernel modules
  5. Restart GPU services

Environment variables:
  ISVCTL_DEMO_MODE=1   Return dummy success without touching the node.
  NODE_SSH_USER        SSH user (default: ubuntu); overrides --ssh-user.
  NODE_SSH_KEY         Path to SSH private key; overrides --ssh-key.
  NODE_SSH_PASS        SSH password (used when no key is available).
  KUBECTL              kubectl binary override (default: kubectl).

Kubernetes / EKS safety sequence (applied automatically when --machine-id is used):
  kubectl cordon   → drain (--ignore-daemonsets --delete-emptydir-data)
  → AHR reset → kubectl uncordon (always runs, even on reset failure)
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time

import paramiko

DEMO_MODE = os.environ.get("ISVCTL_DEMO_MODE") == "1"
KUBECTL: list[str] = shlex.split(os.environ.get("KUBECTL", "kubectl"))
_NODE_SSH_PASS: str = os.environ.get("NODE_SSH_PASS", "")

# GPU services to stop before the reset and restart after.
_GPU_SERVICES = [
    "nvidia-fabricmanager",
    "nvidia-imex",
    "nvidia-persistenced",
    "nvsm",
    "nvidia-dcgm",
]

# Kernel modules — unloaded in this order, reloaded in reverse.
# Dependent modules (EFA peer memory, GPUDirect Storage, GDRCopy) must be
# unloaded before nvidia; rmmod uses `|| true` so absent modules are no-ops.
_NVIDIA_MODULES = [
    "nvidia_drm",
    "nvidia_modeset",
    "nvidia_uvm",
    "efa_nv_peermem",  # AWS EFA GPUDirect RDMA
    "nvidia_fs",  # GPUDirect Storage
    "gdrdrv",  # GDRCopy
    "nvidia",
]


# ---------------------------------------------------------------------------
# SSH helpers
# ---------------------------------------------------------------------------


def _resolve_ssh(args: argparse.Namespace) -> tuple[str, str, str]:
    """Return (host, user, key) from args, env overrides, or kubectl node IP."""
    user = os.environ.get("NODE_SSH_USER") or args.ssh_user or "ubuntu"
    key = os.environ.get("NODE_SSH_KEY") or args.ssh_key or ""

    host = args.host
    if not host and args.machine_id:
        # Kubernetes: resolve node's InternalIP via kubectl.
        proc = subprocess.run(
            [
                *KUBECTL,
                "get",
                "node",
                args.machine_id,
                "-o",
                'jsonpath={.status.addresses[?(@.type=="InternalIP")].address}',
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        host = proc.stdout.strip()
        if not host:
            raise RuntimeError(
                f"Could not resolve InternalIP for node {args.machine_id!r}. "
                "Is kubectl configured and the node registered?"
            )

    if not host:
        raise RuntimeError("No target host: provide --host or --machine-id")

    return host, user, key


def _connect(host: str, user: str, key: str) -> paramiko.SSHClient:
    """Open a paramiko SSH connection supporting key, password, or agent auth."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kwargs: dict = dict(hostname=host, username=user, timeout=15)
    if _NODE_SSH_PASS:
        kwargs.update(password=_NODE_SSH_PASS, allow_agent=False, look_for_keys=False)
    elif key:
        kwargs.update(key_filename=key, allow_agent=False, look_for_keys=False)
    client.connect(**kwargs)
    return client


def _wait_for_ssh(host: str, user: str, key: str, timeout: int = 300, interval: int = 10) -> None:
    """Poll until SSH is accepting connections, or raise RuntimeError on timeout.

    Used for freshly provisioned bare-metal instances where EC2 status checks
    pass before sshd is ready to accept connections.
    """
    deadline = time.time() + timeout
    last_exc: Exception = RuntimeError("SSH wait timed out before first attempt")
    while time.time() < deadline:
        try:
            _connect(host, user, key).close()
            return
        except (OSError, paramiko.SSHException) as exc:
            last_exc = exc
            time.sleep(interval)
    raise RuntimeError(f"SSH not ready on {host} after {timeout}s: {last_exc}")


def _wait_for_nvidia_driver(host: str, user: str, key: str, timeout: int = 300, interval: int = 15) -> None:
    """Poll until nvidia-smi exits 0, meaning the kernel driver is communicating.

    On freshly booted DLAMI bare-metal instances the NVIDIA kernel module can
    finish initializing 30-90s after sshd accepts connections. Running the GPU
    reset before the driver is ready causes nvidia-smi -r to fail immediately.
    """
    deadline = time.time() + timeout
    last_out = ""
    while time.time() < deadline:
        client = _connect(host, user, key)
        try:
            rc, out = _run_cmd(client, "nvidia-smi", timeout=30)
        finally:
            client.close()
        if rc == 0:
            return
        last_out = out
        time.sleep(interval)
    raise RuntimeError(f"NVIDIA driver not ready on {host} after {timeout}s. Last nvidia-smi output:\n{last_out}")


def _run_cmd(client: paramiko.SSHClient, cmd: str, timeout: int = 60) -> tuple[int, str]:
    """Run a command on the open SSH client and return (exit_code, combined output)."""
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    rc = stdout.channel.recv_exit_status()
    return rc, (stdout.read().decode() + stderr.read().decode()).strip()


# ---------------------------------------------------------------------------
# Kubernetes node lifecycle (cordon / drain / uncordon)
# ---------------------------------------------------------------------------


def _kubectl(args: list[str], timeout: int = 30) -> tuple[int, str]:
    """Run a kubectl command and return (exit_code, combined output)."""
    proc = subprocess.run(
        [*KUBECTL, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def _cordon(node: str) -> None:
    rc, out = _kubectl(["cordon", node])
    if rc != 0:
        raise RuntimeError(f"kubectl cordon {node} failed (exit {rc}): {out}")


def _drain(node: str) -> None:
    rc, out = _kubectl(
        ["drain", node, "--ignore-daemonsets", "--delete-emptydir-data", "--timeout=300s"],
        timeout=360,
    )
    if rc != 0:
        raise RuntimeError(f"kubectl drain {node} failed (exit {rc}): {out}")


def _uncordon(node: str) -> None:
    _kubectl(["uncordon", node])  # best-effort; never raise


_RESET_TAINT = "reset-in-progress=true:NoExecute"
_RESET_TAINT_REMOVE = "reset-in-progress-"

# Explicit nvidia device paths for fuser/lsof — glob expansion is unreliable
# over SSH and may miss /dev/nvidia-uvm even when the module is loaded.
_NVIDIA_DEVICES = [
    "/dev/nvidiactl",
    "/dev/nvidia-modeset",
    "/dev/nvidia-uvm",
    "/dev/nvidia-uvm-tools",
    *[f"/dev/nvidia{i}" for i in range(8)],
]


def _apply_reset_taint(node: str) -> None:
    _kubectl(["taint", "node", node, _RESET_TAINT, "--overwrite"], timeout=30)  # best-effort


def _remove_reset_taint(node: str) -> None:
    _kubectl(["taint", "node", node, _RESET_TAINT_REMOVE], timeout=30)  # best-effort


def _pre_reset_k8s(node: str) -> list[str]:
    """Apply a NoExecute taint to signal DaemonSet eviction; do NOT poll.

    Polling is omitted because gpu-operator DaemonSets may carry wildcard
    tolerations (operator: Exists) that let them survive any taint.  Instead
    the k8s reset path (_run_reset_k8s) kills processes directly on the node
    via SSH after applying the taint; lsof output in diagnostics shows what
    remains if nvidia-smi -r still fails.
    """
    lines: list[str] = []
    lines.append(f"=== Pre-reset: applying taint {_RESET_TAINT!r} ===")
    _apply_reset_taint(node)
    lines.append("taint applied (DaemonSets without wildcard tolerations will be evicted)")
    time.sleep(5)  # brief grace period for cooperative shutdown
    return lines


def _post_reset_k8s(node: str) -> list[str]:
    """Poll until nvidia.com/gpu capacity is restored after the reset."""
    lines: list[str] = []

    # Poll nvidia.com/gpu capacity until > 0 (device plugin re-detects GPUs after DaemonSet recreates pods).
    lines.append("=== Waiting for GPU capacity to be re-advertised ===")
    deadline = time.monotonic() + 300
    gpu_count = 0
    while time.monotonic() < deadline:
        time.sleep(10)
        _, cap = _kubectl(
            ["get", "node", node, "-o", r"jsonpath={.status.capacity.nvidia\.com/gpu}"],
        )
        gpu_count = int(cap.strip()) if cap.strip().isdigit() else 0
        if gpu_count > 0:
            break

    if gpu_count == 0:
        raise RuntimeError(
            f"nvidia.com/gpu capacity still 0 on {node} after 300s — device plugin did not re-advertise GPUs"
        )
    lines.append(f"nvidia.com/gpu capacity restored: {gpu_count}")
    return lines


# ---------------------------------------------------------------------------
# Reset sequences
# ---------------------------------------------------------------------------


def _run_reset_k8s(host: str, user: str, key: str) -> dict[str, object]:
    """k8s-specific reset: service stop + explicit fuser-k + nvidia-smi -r.

    Skips rmmod/modprobe: modules can't be cleanly unloaded when DaemonSet
    pods tolerate the NoExecute taint and keep restarting.  nvidia-smi -r
    does not require module reload — it resets the hardware directly.

    Includes lsof diagnostics before and after failure so the next debug
    iteration can identify the exact process holding the device.
    """
    lines: list[str] = []
    client = _connect(host, user, key)

    def run(cmd: str, timeout: int = 60) -> str:
        _, out = _run_cmd(client, cmd, timeout=timeout)
        return out or "ok"

    try:
        # 1. Stop GPU services.
        lines.append("=== Stopping GPU services ===")
        for svc in _GPU_SERVICES:
            out = run(f"sudo systemctl stop {svc} 2>/dev/null || true")
            lines.append(f"stop {svc}: {out}")
        time.sleep(3)

        # 2. Diagnostic: what still holds nvidia device files?
        lines.append("=== lsof /dev/nvidia-uvm /dev/nvidiactl ===")
        devs = " ".join(d for d in _NVIDIA_DEVICES if "uvm" in d or "ctl" in d)
        out = run(f"sudo lsof {devs} 2>/dev/null | head -30 || echo none", timeout=20)
        lines.append(out)

        # 3. Force-close all handles with explicit device paths.
        lines.append("=== Killing all nvidia device users ===")
        existing = run(
            "for d in " + " ".join(_NVIDIA_DEVICES) + '; do [ -e "$d" ] && echo "$d"; done',
            timeout=10,
        )
        lines.append(f"devices present: {existing}")
        out = run(
            "sudo fuser -k " + " ".join(_NVIDIA_DEVICES) + " 2>/dev/null; echo done",
            timeout=30,
        )
        lines.append(out)
        time.sleep(3)

        # 4. GPU reset (best-effort — PCIe FLR may be blocked on cloud platforms).
        lines.append("=== GPU reset ===")
        flr_rc, reset_out = _run_cmd(client, "sudo nvidia-smi -r", timeout=120)
        lines.append(reset_out)
        flr_supported = flr_rc == 0
        if not flr_supported:
            _, diag = _run_cmd(
                client,
                "sudo lsof " + " ".join(_NVIDIA_DEVICES) + " 2>/dev/null | head -20 || echo none",
                timeout=15,
            )
            lines.append(f"=== Post-reset lsof ===\n{diag}")
            lines.append(
                f"nvidia-smi -r exit {flr_rc} — PCIe FLR not supported on this platform; "
                "verifying GPU accessibility directly"
            )

        # 5. Verify GPUs accessible — authoritative gate for both FLR and non-FLR paths.
        lines.append("=== Verifying GPU accessibility ===")
        verify_rc, smi_out = _run_cmd(client, "nvidia-smi", timeout=60)
        lines.append(smi_out)
        if verify_rc != 0:
            diag_str = "\n".join(lines)
            raise RuntimeError(f"GPUs not accessible after reset\nDIAGNOSTICS:\n{diag_str}")

        # 6. Restart GPU services.
        lines.append("=== Starting GPU services ===")
        for svc in _GPU_SERVICES:
            out = run(f"sudo systemctl start {svc} 2>/dev/null || true")
            lines.append(f"start {svc}: {out or 'ok'}")
    finally:
        client.close()

    return {
        "requested": True,
        "completed": True,
        "flr_reset": flr_supported,
        "node_id": host,
        "message": "\n".join(lines),
    }


def _run_reset(host: str, user: str, key: str) -> dict[str, object]:
    """Execute the GPU reset sequence on the node and return a result dict."""
    lines: list[str] = []
    client = _connect(host, user, key)

    def run(cmd: str, timeout: int = 60) -> str:
        _, out = _run_cmd(client, cmd, timeout=timeout)
        return out or "ok"

    try:
        # 1. Stop GPU services.
        lines.append("=== Stopping GPU services ===")
        for svc in _GPU_SERVICES:
            out = run(f"sudo systemctl stop {svc} 2>/dev/null || true")
            lines.append(f"stop {svc}: {out}")
        time.sleep(5)

        # Kill any remaining processes holding nvidia device fds open.
        # nvidia-fabricmanager and nvidia-persistenced may not fully flush before
        # rmmod sees them; fuser -k forces the remaining handles closed.
        lines.append("=== Killing remaining nvidia device users ===")
        out = run("sudo fuser -k /dev/nvidia* /dev/nvidiactl 2>/dev/null; echo done", timeout=30)
        lines.append(out)
        time.sleep(2)

        # 2. PCIe FLR (best-effort — must run while the driver is still loaded so
        #    NVML has an interface; blocked on cloud platforms such as AWS EC2).
        lines.append("=== GPU reset (FLR) ===")
        flr_rc, reset_out = _run_cmd(client, "sudo nvidia-smi -r", timeout=300)
        lines.append(reset_out)
        flr_supported = flr_rc == 0
        if not flr_supported:
            lines.append(
                f"nvidia-smi -r exit {flr_rc} — PCIe FLR not supported on this platform; "
                "proceeding with module reload as the reset mechanism"
            )

        # 3. Unload nvidia kernel modules (dependency order).
        lines.append("=== Unloading nvidia modules ===")
        for mod in _NVIDIA_MODULES:
            out = run(f"sudo rmmod {mod} 2>&1 || true")
            lines.append(f"rmmod {mod}: {out or 'ok'}")

        # 4. Reload nvidia modules (reverse order).
        lines.append("=== Reloading nvidia modules ===")
        for mod in reversed(_NVIDIA_MODULES):
            out = run(f"sudo modprobe {mod} 2>&1 || true")
            lines.append(f"modprobe {mod}: {out or 'ok'}")

        # 5. Verify GPUs accessible after reload — this is the authoritative gate.
        lines.append("=== Verifying GPU accessibility ===")
        verify_rc, smi_out = _run_cmd(client, "nvidia-smi", timeout=60)
        lines.append(smi_out)
        if verify_rc != 0:
            diag = "\n".join(lines)
            raise RuntimeError(f"GPUs not accessible after module reload\nDIAGNOSTICS:\n{diag}")

        # 6. Restart GPU services.
        lines.append("=== Starting GPU services ===")
        for svc in _GPU_SERVICES:
            out = run(f"sudo systemctl start {svc} 2>/dev/null || true")
            lines.append(f"start {svc}: {out or 'ok'}")
    finally:
        client.close()

    return {
        "requested": True,
        "completed": True,
        "flr_reset": flr_supported,
        "node_id": host,
        "message": "\n".join(lines),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    """Parse arguments, perform the GPU reset via SSH, and emit JSON."""
    parser = argparse.ArgumentParser(description="Reset GPUs on a node via SSH (BFX01-01)")
    # Provider-agnostic SSH target.
    parser.add_argument("--host", default="", nargs="?", const="", help="Node IP or hostname (bare metal / AWS)")
    parser.add_argument("--ssh-user", default="", nargs="?", const="", help="SSH user (default: ubuntu)")
    parser.add_argument("--ssh-key", default="", nargs="?", const="", help="Path to SSH private key")
    # Kubernetes target (alternative to --host).
    parser.add_argument("--machine-id", default="", nargs="?", const="", help="Kubernetes node name (k8s provider)")
    # Accepted for provider compatibility; unused beyond JSON output.
    parser.add_argument("--region", default="", nargs="?", const="")
    parser.add_argument(
        "--provider", default="", nargs="?", const="", help="Provider name for JSON output (e.g. aws, my-isv)"
    )

    args = parser.parse_args()
    provider = args.provider or "bare-metal"
    node_label = args.machine_id or args.host or "demo-node-001"

    if DEMO_MODE:
        print(
            json.dumps(
                {
                    "success": True,
                    "platform": provider,
                    "operation": {"requested": True, "completed": True, "node_id": node_label},
                },
                indent=2,
            )
        )
        return 0

    if not args.host and not args.machine_id:
        print(
            json.dumps(
                {
                    "success": True,
                    "platform": provider,
                    "skipped": True,
                    "skip_reason": "no target: provide --host or --machine-id to run GPU reset",
                },
                indent=2,
            )
        )
        return 0

    try:
        host, user, key = _resolve_ssh(args)
        if args.machine_id:
            # k8s / EKS:
            #   cordon → drain → taint(NoExecute) → reset
            #   finally: untaint + uncordon  ← must happen BEFORE capacity poll
            #   then: poll nvidia.com/gpu capacity (DaemonSet pods can now reschedule)
            _cordon(args.machine_id)
            try:
                _drain(args.machine_id)
                pre_lines = _pre_reset_k8s(args.machine_id)
                operation = _run_reset_k8s(host, user, key)
                operation["message"] = "\n".join(pre_lines) + "\n" + str(operation.get("message", ""))
            finally:
                # Remove taint and uncordon here so the device-plugin DaemonSet pod
                # can reschedule before _post_reset_k8s starts polling capacity.
                _remove_reset_taint(args.machine_id)
                _uncordon(args.machine_id)
            # _post_reset_k8s only runs if _run_reset_k8s succeeded (no exception);
            # if it raised, the exception propagated through finally and is caught below.
            post_lines = _post_reset_k8s(args.machine_id)
            operation["message"] = str(operation.get("message", "")) + "\n" + "\n".join(post_lines)
        else:
            _wait_for_ssh(host, user, key)
            _wait_for_nvidia_driver(host, user, key)
            operation = _run_reset(host, user, key)
        print(json.dumps({"success": True, "platform": provider, "operation": operation}, indent=2))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "success": False,
                    "platform": provider,
                    "operation": {"requested": True, "completed": False, "node": node_label},
                    "error": str(exc),
                },
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
