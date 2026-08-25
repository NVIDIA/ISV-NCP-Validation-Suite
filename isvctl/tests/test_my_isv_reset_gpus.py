# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the my-isv SSH-based GPU reset script (BFX01-01)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "configs/providers/shared/reset_gpus.py"


def _load(monkeypatch: pytest.MonkeyPatch, *, demo: bool) -> ModuleType:
    """Import reset_gpus fresh so module-level DEMO_MODE is re-evaluated."""
    monkeypatch.setenv("ISVCTL_DEMO_MODE", "1" if demo else "0")
    monkeypatch.syspath_prepend(str(_SCRIPT.parent.parent))
    spec = importlib.util.spec_from_file_location("reset_gpus", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _fake_client(*, fail_reset: bool = False) -> MagicMock:
    """Return a mock paramiko SSHClient whose exec_command mimics a GPU node.

    When fail_reset=True, only ``nvidia-smi -r`` fails (exit 255), simulating
    a platform where PCIe FLR is blocked (e.g. AWS EC2).  All other commands,
    including the post-reload ``nvidia-smi`` verify, succeed — so the overall
    reset still completes with ``flr_reset: false``.  _wait_for_nvidia_driver
    is stubbed in _run() so its nvidia-smi call never reaches this mock.
    """
    client = MagicMock()

    def exec_command(cmd: str, timeout: Any = None) -> tuple[Any, MagicMock, MagicMock]:
        """Return mock channel objects; fails nvidia-smi -r when fail_reset is set."""
        if "nvidia-smi -r" in cmd and fail_reset:
            stdout = MagicMock()
            stdout.read.return_value = b""
            stdout.channel.recv_exit_status.return_value = 255
            stderr = MagicMock()
            stderr.read.return_value = b"In use by another client"
        else:
            stdout = MagicMock()
            stdout.read.return_value = b"ok"
            stdout.channel.recv_exit_status.return_value = 0
            stderr = MagicMock()
            stderr.read.return_value = b""
        return MagicMock(), stdout, stderr

    client.exec_command.side_effect = exec_command
    return client


def _run(
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    *,
    demo: bool,
    fail_reset: bool = False,
    kubectl_ip: str = "10.0.0.2",
) -> tuple[int, dict[str, Any]]:
    """Run main() and return (exit_code, parsed_json_output)."""
    mod = _load(monkeypatch, demo=demo)
    monkeypatch.setattr(sys, "argv", ["reset_gpus.py", *argv])
    monkeypatch.setattr("time.sleep", lambda _: None)

    # kubectl node IP resolution (subprocess stays for kubectl).
    def fake_subprocess_run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 0, kubectl_ip, "")

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    # Stub SSH/driver readiness polls so tests don't wait on real timeouts.
    monkeypatch.setattr(mod, "_wait_for_ssh", lambda host, user, key, **kw: None)
    monkeypatch.setattr(mod, "_wait_for_nvidia_driver", lambda host, user, key, **kw: None)

    # Stub out k8s node lifecycle so tests don't need a real cluster.
    monkeypatch.setattr(mod, "_cordon", lambda node: None)
    monkeypatch.setattr(mod, "_drain", lambda node: None)
    monkeypatch.setattr(mod, "_apply_reset_taint", lambda node: None)
    monkeypatch.setattr(mod, "_remove_reset_taint", lambda node: None)
    monkeypatch.setattr(mod, "_uncordon", lambda node: None)
    monkeypatch.setattr(mod, "_pre_reset_k8s", lambda node: ["taint applied"])
    monkeypatch.setattr(
        mod,
        "_run_reset_k8s",
        lambda host, user, key: {"requested": True, "completed": True, "node_id": host, "message": "k8s reset ok"},
    )
    monkeypatch.setattr(mod, "_post_reset_k8s", lambda node: ["nvidia.com/gpu capacity restored: 4"])

    # Paramiko SSH — mock _connect so no real network calls are made.
    client = _fake_client(fail_reset=fail_reset)
    monkeypatch.setattr(mod, "_connect", lambda host, user, key: client)

    captured: list[str] = []
    monkeypatch.setattr("builtins.print", lambda *a, **kw: captured.append(str(a[0])))

    exit_code = mod.main()
    output = json.loads("\n".join(captured))
    return exit_code, output


# ---------------------------------------------------------------------------
# Demo mode
# ---------------------------------------------------------------------------


class TestDemoMode:
    """ISVCTL_DEMO_MODE=1 must return success without touching the node."""

    def test_exits_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        code, _ = _run(monkeypatch, [], demo=True)
        assert code == 0

    def test_success_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _, out = _run(monkeypatch, [], demo=True)
        assert out["success"] is True

    def test_operation_completed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _, out = _run(monkeypatch, [], demo=True)
        assert out["operation"]["completed"] is True

    def test_uses_machine_id_as_node_label(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _, out = _run(monkeypatch, ["--machine-id", "gpu-node-01"], demo=True)
        assert out["operation"]["node_id"] == "gpu-node-01"

    def test_uses_host_as_node_label(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _, out = _run(monkeypatch, ["--host", "10.0.0.1"], demo=True)
        assert out["operation"]["node_id"] == "10.0.0.1"

    def test_platform_reflects_provider_arg(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The --provider argument controls the platform field in the output."""
        _, out = _run(monkeypatch, ["--provider", "my-isv"], demo=True)
        assert out["platform"] == "my-isv"

    def test_output_satisfies_gpu_reset_check(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Demo output must satisfy the GpuResetCheck contract fields."""
        _, out = _run(monkeypatch, ["--host", "10.0.0.1"], demo=True)
        assert out["success"] is True
        assert out["operation"]["completed"] is True
        assert out["operation"]["node_id"] == "10.0.0.1"


# ---------------------------------------------------------------------------
# Real mode — happy path (all SSH commands succeed)
# ---------------------------------------------------------------------------


class TestRealModeSuccess:
    """Mocked paramiko client returning success for all commands."""

    def test_exits_zero_with_host(self, monkeypatch: pytest.MonkeyPatch) -> None:
        code, _ = _run(monkeypatch, ["--host", "10.0.0.1", "--ssh-key", "/tmp/key.pem"], demo=False)
        assert code == 0

    def test_exits_zero_with_machine_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """k8s provider: machine-id resolves to node IP via kubectl."""
        code, _ = _run(monkeypatch, ["--machine-id", "gpu-node-01"], demo=False)
        assert code == 0

    def test_success_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _, out = _run(monkeypatch, ["--host", "10.0.0.1"], demo=False)
        assert out["success"] is True

    def test_operation_completed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _, out = _run(monkeypatch, ["--host", "10.0.0.1"], demo=False)
        assert out["operation"]["completed"] is True


# ---------------------------------------------------------------------------
# Real mode — nvidia-smi -r failure
# ---------------------------------------------------------------------------


class TestRealModeFLRBlocked:
    """When nvidia-smi -r fails the reset still completes via module reload."""

    def test_exits_zero_when_flr_blocked(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """FLR failure is non-fatal; module reload is the real reset mechanism."""
        code, _ = _run(monkeypatch, ["--host", "10.0.0.1"], demo=False, fail_reset=True)
        assert code == 0

    def test_success_true_when_flr_blocked(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Overall success is True because module reload recovers the GPU."""
        _, out = _run(monkeypatch, ["--host", "10.0.0.1"], demo=False, fail_reset=True)
        assert out["success"] is True

    def test_flr_reset_false_when_flr_blocked(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """flr_reset records whether PCIe FLR was available on the platform."""
        _, out = _run(monkeypatch, ["--host", "10.0.0.1"], demo=False, fail_reset=True)
        assert out["operation"]["flr_reset"] is False


# ---------------------------------------------------------------------------
# No target host
# ---------------------------------------------------------------------------


class TestNoTarget:
    """When neither --host nor --machine-id is provided the script must exit cleanly."""

    def test_skips_when_no_host_or_machine_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No --host or --machine-id → structured skip (exit 0, skipped: true)."""
        code, out = _run(monkeypatch, [], demo=False, kubectl_ip="")
        assert code == 0
        assert out["skipped"] is True
