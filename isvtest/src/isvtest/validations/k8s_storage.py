# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""CSI storage validations (K8S23).

Currently implements :class:`K8sCsiStorageTypesCheck` (K8S23-04), which verifies
that the cluster exposes a StorageClass for each of block / shared filesystem /
NFS storage and that a PVC binds against each configured class.
"""

from __future__ import annotations

import shlex
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, ClassVar

from isvtest.config.settings import (
    get_k8s_csi_block_storage_class,
    get_k8s_csi_nfs_storage_class,
    get_k8s_csi_shared_fs_storage_class,
)
from isvtest.core.k8s import (
    get_kubectl_base_shell,
    get_kubectl_command,
    render_k8s_manifest,
)
from isvtest.core.validation import BaseValidation

_MANIFEST_DIR = Path(__file__).parent / "manifests" / "k8s"
_PVC_MANIFEST = _MANIFEST_DIR / "storage_pvc.yaml"

_STORAGE_TYPES: tuple[tuple[str, str], ...] = (
    ("block", "ReadWriteOnce"),
    ("shared-fs", "ReadWriteMany"),
    ("nfs", "ReadWriteMany"),
)


def _poll_pvc_bound(run_command, kubectl_base: str, namespace: str, pvc_name: str, timeout_s: int) -> bool:
    """Poll ``kubectl get pvc`` until ``status.phase == "Bound"`` or timeout."""
    deadline = time.time() + timeout_s
    cmd = f"{kubectl_base} get pvc {shlex.quote(pvc_name)} -n {shlex.quote(namespace)} -o jsonpath='{{.status.phase}}'"
    while time.time() < deadline:
        result = run_command(cmd)
        if result.exit_code == 0 and result.stdout.strip().strip("'") == "Bound":
            return True
        time.sleep(2.0)
    return False


def _apply_mount_pod_manifest(
    kubectl_parts: list[str],
    namespace: str,
    pod_name: str,
    pvc_name: str,
    timeout: float,
) -> tuple[int, str]:
    """Render the BusyBox mount-pod manifest for ``pvc_name`` and ``kubectl apply`` it.

    Storage classes with ``volumeBindingMode: WaitForFirstConsumer`` (the
    default for AWS EBS, GCE PD, Azure Disk, etc.) keep the PVC ``Pending``
    until a pod referencing it is scheduled, so every check that needs the
    PVC to reach ``Bound`` must land a consumer alongside it.
    """

    def _mutate(doc: dict[str, Any]) -> dict[str, Any]:
        return _set_mount_pod_fields(doc, namespace=namespace, name=pod_name, pvc_name=pvc_name)

    return _apply_manifest(kubectl_parts, render_k8s_manifest(_MOUNT_POD_MANIFEST, _mutate), timeout)


def _wait_pod_ready(run_command, kubectl_base: str, namespace: str, pod_name: str, timeout_s: int) -> tuple[bool, str]:
    """``kubectl wait --for=condition=Ready`` for ``pod_name``; return (ok, stderr_or_stdout)."""
    cmd = (
        f"{kubectl_base} wait --for=condition=Ready "
        f"--timeout={timeout_s}s -n {shlex.quote(namespace)} pod/{shlex.quote(pod_name)}"
    )
    result = run_command(cmd)
    if result.exit_code == 0:
        return True, ""
    return False, (result.stderr.strip() or result.stdout.strip())


class K8sCsiStorageTypesCheck(BaseValidation):
    """Verify CSI supports block, shared filesystem, and NFS storage (K8S23-04).

    For each configured storage type, two subtests run:

    * ``sc-exists[<type>]`` — the named StorageClass is visible to kubectl.
    * ``pvc-binds[<type>]`` — a fresh PVC against that StorageClass reaches
      ``Bound`` within ``bind_timeout_s``. A BusyBox consumer pod is
      scheduled alongside the PVC so this also works for StorageClasses
      with ``volumeBindingMode: WaitForFirstConsumer`` (the default for
      most cloud block CSIs).

    Types with no configured StorageClass are reported as skipped, so the
    check is safe to enable on every provider; pass iff every configured type
    passes both subtests.

    Config keys (with defaults):
        block_storage_class: StorageClass for block (RWO) storage
            (default: from :func:`get_k8s_csi_block_storage_class`).
        shared_fs_storage_class: StorageClass for shared filesystem (RWX)
            (default: from :func:`get_k8s_csi_shared_fs_storage_class`).
        nfs_storage_class: StorageClass for NFS (RWX)
            (default: from :func:`get_k8s_csi_nfs_storage_class`).
        pvc_size: Requested capacity for each probe PVC (default: ``1Gi``).
        bind_timeout_s: Max wait for each PVC to reach ``Bound`` (default: 120).
        namespace_prefix: Prefix for the ephemeral namespace
            (default: ``isvtest-csi-types``).
        timeout: Overall class-level timeout for each ``run_command`` call
            (default: 300).
    """

    description: ClassVar[str] = "Verify CSI supports block, shared filesystem, and NFS storage classes (K8S23-04)."
    timeout: ClassVar[int] = 300
    markers: ClassVar[list[str]] = ["kubernetes"]

    def run(self) -> None:
        """Create an ephemeral namespace, probe each configured storage type, and record subtests."""
        self._kubectl_parts = get_kubectl_command()
        self._kubectl_base = get_kubectl_base_shell()
        bind_timeout = int(self.config.get("bind_timeout_s", 120))
        namespace_prefix = self.config.get("namespace_prefix", "isvtest-csi-types")
        pvc_size = str(self.config.get("pvc_size", "1Gi"))

        configured: dict[str, str] = {}
        for type_name, _ in _STORAGE_TYPES:
            sc_name = self.config.get(f"{type_name.replace('-', '_')}_storage_class") or _env_fallback(type_name)
            if sc_name:
                configured[type_name] = sc_name

        if not configured:
            self.set_passed("Skipped: no StorageClass configured for block/shared-fs/nfs")
            return

        self._namespace = f"{namespace_prefix}-{uuid.uuid4().hex[:8]}"
        ns_quoted = shlex.quote(self._namespace)
        ns_created = False
        try:
            ns_result = self.run_command(f"{self._kubectl_base} create namespace {ns_quoted}")
            if ns_result.exit_code != 0:
                self.set_failed(f"Failed to create namespace {self._namespace}: {ns_result.stderr}")
                return
            ns_created = True

            any_failed = False
            covered: list[str] = []

            for type_name, access_mode in _STORAGE_TYPES:
                sc_name = configured.get(type_name)
                if not sc_name:
                    self.report_subtest(
                        f"sc-exists[{type_name}]",
                        passed=True,
                        message=f"{type_name} StorageClass not configured",
                        skipped=True,
                    )
                    self.report_subtest(
                        f"pvc-binds[{type_name}]",
                        passed=True,
                        message=f"{type_name} StorageClass not configured",
                        skipped=True,
                    )
                    continue

                sc_result = self.run_command(f"{self._kubectl_base} get storageclass {shlex.quote(sc_name)} -o name")
                sc_ok = sc_result.exit_code == 0
                self.report_subtest(
                    f"sc-exists[{type_name}]",
                    passed=sc_ok,
                    message=(
                        f"StorageClass {sc_name!r} found"
                        if sc_ok
                        else f"StorageClass {sc_name!r} missing: {sc_result.stderr.strip() or sc_result.stdout.strip()}"
                    ),
                )
                if not sc_ok:
                    any_failed = True
                    # Skip the paired pvc-binds subtest so the overall ratio
                    # still reflects one failure per broken storage type.
                    self.report_subtest(
                        f"pvc-binds[{type_name}]",
                        passed=True,
                        message=f"StorageClass {sc_name!r} missing; PVC probe skipped",
                        skipped=True,
                    )
                    continue

                pvc_name = f"csi-types-{type_name}-{uuid.uuid4().hex[:6]}"
                pod_name = f"csi-types-{type_name}-{uuid.uuid4().hex[:6]}"
                if not self._apply_pvc(pvc_name, sc_name, access_mode, pvc_size):
                    any_failed = True
                    self.report_subtest(
                        f"pvc-binds[{type_name}]",
                        passed=False,
                        message=f"kubectl apply failed for PVC {pvc_name!r} ({sc_name}, {access_mode})",
                    )
                    continue

                pod_rc, pod_err = _apply_mount_pod_manifest(
                    self._kubectl_parts, self._namespace, pod_name, pvc_name, self.timeout
                )
                if pod_rc != 0:
                    any_failed = True
                    self.report_subtest(
                        f"pvc-binds[{type_name}]",
                        passed=False,
                        message=(
                            f"kubectl apply failed for consumer pod {pod_name!r} "
                            f"({sc_name}, {access_mode}): {pod_err.strip()[:200]}"
                        ),
                    )
                    continue

                pod_ready, wait_err = _wait_pod_ready(
                    self.run_command, self._kubectl_base, self._namespace, pod_name, bind_timeout
                )
                bound = pod_ready and self._wait_pvc_bound(pvc_name, 5)
                self.report_subtest(
                    f"pvc-binds[{type_name}]",
                    passed=bound,
                    message=(
                        f"PVC {pvc_name!r} bound against {sc_name} ({access_mode}) via consumer pod {pod_name!r}"
                        if bound
                        else (
                            f"PVC {pvc_name!r} did not reach Bound via consumer pod {pod_name!r} "
                            f"within {bind_timeout}s ({sc_name}, {access_mode}): {wait_err[:200]}"
                        )
                    ),
                )
                if bound:
                    covered.append(type_name)
                else:
                    any_failed = True

            if any_failed:
                self.set_failed("One or more CSI storage-type subtests failed; see subtest details")
            else:
                self.set_passed(f"CSI supports storage types: {', '.join(sorted(covered))}")
        finally:
            # Cleanup must never overwrite pass/fail outcome set above.
            if ns_created:
                cleanup = self.run_command(
                    f"{self._kubectl_base} delete namespace {ns_quoted} --wait=false --ignore-not-found=true"
                )
                if cleanup.exit_code != 0:
                    self.log.warning("Namespace cleanup failed for %s: %s", self._namespace, cleanup.stderr)

    def _apply_pvc(self, name: str, sc_name: str, access_mode: str, size: str) -> bool:
        """Render the PVC manifest and apply it; return True on success."""

        def _mutate(doc: dict[str, Any]) -> dict[str, Any]:
            return _set_pvc_fields(doc, namespace=self._namespace, name=name, sc=sc_name, mode=access_mode, size=size)

        manifest = render_k8s_manifest(_PVC_MANIFEST, _mutate)
        try:
            proc = subprocess.run(
                self._kubectl_parts + ["apply", "-f", "-"],
                input=manifest,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            self.log.error("kubectl apply timed out for PVC %s", name)
            return False
        except Exception as exc:
            self.log.error("kubectl apply failed for PVC %s: %s", name, exc)
            return False

        if proc.returncode != 0:
            self.log.error(
                "kubectl apply failed for PVC %s: %s",
                name,
                proc.stderr.strip() or proc.stdout.strip(),
            )
            return False
        return True

    def _wait_pvc_bound(self, pvc_name: str, timeout_s: int) -> bool:
        return _poll_pvc_bound(self.run_command, self._kubectl_base, self._namespace, pvc_name, timeout_s)


def _set_pvc_fields(
    doc: dict[str, Any],
    *,
    namespace: str,
    name: str,
    sc: str,
    mode: str,
    size: str,
) -> dict[str, Any]:
    """Mutate a parsed PVC manifest in place with the requested fields."""
    metadata = doc.setdefault("metadata", {})
    metadata["name"] = name
    metadata["namespace"] = namespace

    spec = doc.setdefault("spec", {})
    spec["storageClassName"] = sc
    spec["accessModes"] = [mode]
    resources = spec.setdefault("resources", {})
    requests = resources.setdefault("requests", {})
    requests["storage"] = size
    return doc


def _env_fallback(type_name: str) -> str:
    """Return the env-backed StorageClass default for a given storage type."""
    if type_name == "block":
        return get_k8s_csi_block_storage_class()
    if type_name == "shared-fs":
        return get_k8s_csi_shared_fs_storage_class()
    if type_name == "nfs":
        return get_k8s_csi_nfs_storage_class()
    return ""
