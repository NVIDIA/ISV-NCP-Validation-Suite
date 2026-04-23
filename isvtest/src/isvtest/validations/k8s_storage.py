# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""CSI storage validations (K8S23).

Implements:

* :class:`K8sCsiStorageTypesCheck` (K8S23-04) — verify the cluster exposes a
  StorageClass for each of block / shared filesystem / NFS storage and that
  a PVC binds against each configured class.
* :class:`K8sCsiStorageQuotaApiCheck` (K8S23-07) — verify Kubernetes-native
  APIs expose storage quota and per-PVC/PV usage.
"""

from __future__ import annotations

import json
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
_RESOURCEQUOTA_MANIFEST = _MANIFEST_DIR / "storage_resourcequota.yaml"

_STORAGE_TYPES: tuple[tuple[str, str], ...] = (
    ("block", "ReadWriteOnce"),
    ("shared-fs", "ReadWriteMany"),
    ("nfs", "ReadWriteMany"),
)

_QUOTA_REJECTION_TOKENS: tuple[str, ...] = ("exceeded quota", "forbidden")


def _apply_manifest(kubectl_parts: list[str], manifest: str, timeout: float) -> tuple[int, str]:
    """Invoke ``kubectl apply -f -`` with ``manifest``; return ``(returncode, stderr-or-stdout)``.

    Timeouts and unexpected exceptions are normalised to returncode ``-1`` so
    callers can treat them uniformly as apply failures.
    """
    try:
        proc = subprocess.run(
            kubectl_parts + ["apply", "-f", "-"],
            input=manifest,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return -1, "kubectl apply timed out"
    except Exception as exc:
        return -1, f"kubectl apply raised: {exc}"
    return proc.returncode, proc.stderr or proc.stdout


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


class K8sCsiStorageQuotaApiCheck(BaseValidation):
    """Verify Kubernetes-native APIs expose storage quota and per-PVC/PV usage (K8S23-07).

    Four subtests run against a single ephemeral namespace:

    * ``resourcequota-storage-api`` — a ResourceQuota carrying both
      ``requests.storage`` and
      ``<sc>.storageclass.storage.k8s.io/requests.storage`` lands and its
      ``.status.hard`` publishes both keys.
    * ``per-pvc-usage`` — a PVC against the configured StorageClass binds
      (via a BusyBox consumer pod so this works under
      ``WaitForFirstConsumer``), exposes ``.status.capacity.storage``, and
      its usage is reflected in the ResourceQuota's ``.status.used``.
    * ``quota-enforcement`` — an over-quota PVC is rejected at admission
      with an ``exceeded quota`` / ``forbidden`` message.
    * ``pv-usage-api`` — the bound PV exposes ``.spec.capacity.storage``,
      ``.spec.claimRef.name`` matching the usage PVC, and
      ``.spec.csi.driver``.

    When ``resourcequota-storage-api`` fails, the three downstream subtests
    are reported as skipped because they all require the quota to be in
    place; the overall validation still fails.

    Config keys (with defaults):
        storage_class: StorageClass to use for the probe PVCs; defaults to
            :func:`get_k8s_csi_block_storage_class`. When unset the whole
            check is skipped so it is safe to enable everywhere.
        total_quota: Namespace-wide ``requests.storage`` cap
            (default: ``10Gi``).
        per_sc_quota: Per-StorageClass cap (default: ``5Gi``). Must exceed
            ``pvc_request`` so the usage PVC fits.
        pvc_request: Size requested by the usage PVC (default: ``1Gi``).
        over_quota_request: Size requested by the enforcement PVC; must
            exceed ``per_sc_quota`` so admission rejects it
            (default: ``100Gi``).
        bind_timeout_s: Max wait for the usage PVC to Bind (default: 120).
        quota_settle_s: Max wait for each ``ResourceQuota.status`` section
            (``hard`` and ``used``) to populate (default: 30).
        namespace_prefix: Prefix for the ephemeral namespace
            (default: ``isvtest-csi-quota``).
        timeout: Overall class-level timeout for each ``run_command``
            (default: 300).
    """

    description: ClassVar[str] = "Verify Kubernetes-native APIs expose storage quota and per-PVC/PV usage (K8S23-07)."
    timeout: ClassVar[int] = 300
    markers: ClassVar[list[str]] = ["kubernetes"]

    def run(self) -> None:
        """Drive the four-subtest quota-API probe against a single ephemeral namespace."""
        storage_class = self.config.get("storage_class") or get_k8s_csi_block_storage_class()
        if not storage_class:
            self.set_passed("Skipped: no storage_class configured")
            return

        total_quota = str(self.config.get("total_quota", "10Gi"))
        per_sc_quota = str(self.config.get("per_sc_quota", "5Gi"))
        pvc_request = str(self.config.get("pvc_request", "1Gi"))
        over_quota_request = str(self.config.get("over_quota_request", "100Gi"))
        bind_timeout = int(self.config.get("bind_timeout_s", 120))
        quota_settle = int(self.config.get("quota_settle_s", 30))
        ns_prefix = self.config.get("namespace_prefix", "isvtest-csi-quota")

        self._kubectl_parts = get_kubectl_command()
        self._kubectl_base = get_kubectl_base_shell()
        self._namespace = f"{ns_prefix}-{uuid.uuid4().hex[:8]}"
        ns_quoted = shlex.quote(self._namespace)

        sc_quota_key = f"{storage_class}.storageclass.storage.k8s.io/requests.storage"
        rq_name = f"storage-quota-{uuid.uuid4().hex[:6]}"
        usage_pvc = f"quota-usage-{uuid.uuid4().hex[:6]}"
        over_pvc = f"quota-over-{uuid.uuid4().hex[:6]}"

        ns_created = False
        try:
            ns_result = self.run_command(f"{self._kubectl_base} create namespace {ns_quoted}")
            if ns_result.exit_code != 0:
                self.set_failed(f"Failed to create namespace {self._namespace}: {ns_result.stderr}")
                return
            ns_created = True

            any_failed = False

            quota_ok = self._apply_resourcequota(rq_name, total_quota, sc_quota_key, per_sc_quota)
            hard: dict[str, Any] | None = None
            if quota_ok:
                hard = self._wait_quota_section(rq_name, "hard", [sc_quota_key, "requests.storage"], quota_settle)
                quota_ok = hard is not None

            if quota_ok:
                self.report_subtest(
                    "resourcequota-storage-api",
                    passed=True,
                    message=(
                        f"ResourceQuota {rq_name!r} hard={{requests.storage: {hard.get('requests.storage')!r}, "
                        f"{sc_quota_key}: {hard.get(sc_quota_key)!r}}}"
                        if hard
                        else f"ResourceQuota {rq_name!r} hard populated"
                    ),
                )
            else:
                self.report_subtest(
                    "resourcequota-storage-api",
                    passed=False,
                    message=(
                        f"ResourceQuota {rq_name!r} did not publish hard limits "
                        f"(both {'requests.storage'!r} and {sc_quota_key!r}) within {quota_settle}s"
                    ),
                )
                for dependent in ("per-pvc-usage", "quota-enforcement", "pv-usage-api"):
                    self.report_subtest(
                        dependent,
                        passed=True,
                        message="resourcequota-storage-api failed; dependent probe skipped",
                        skipped=True,
                    )
                self.set_failed("ResourceQuota did not land; downstream quota probes skipped")
                return

            usage_ok = self._run_per_pvc_usage(
                pvc_name=usage_pvc,
                storage_class=storage_class,
                pvc_request=pvc_request,
                rq_name=rq_name,
                sc_quota_key=sc_quota_key,
                bind_timeout=bind_timeout,
                quota_settle=quota_settle,
            )
            if not usage_ok:
                any_failed = True

            if not self._run_quota_enforcement(over_pvc, storage_class, over_quota_request):
                any_failed = True

            # pv-usage-api requires per-pvc-usage to have produced a Bound PVC.
            if usage_ok:
                if not self._run_pv_usage_api(usage_pvc):
                    any_failed = True
            else:
                self.report_subtest(
                    "pv-usage-api",
                    passed=True,
                    message="per-pvc-usage did not produce a bound PV; pv-usage-api skipped",
                    skipped=True,
                )

            if any_failed:
                self.set_failed("One or more storage quota API subtests failed; see subtest details")
            else:
                self.set_passed(f"Storage quota APIs verified against StorageClass {storage_class!r}")
        finally:
            # Cleanup must never overwrite pass/fail outcome set above.
            if ns_created:
                cleanup = self.run_command(
                    f"{self._kubectl_base} delete namespace {ns_quoted} --wait=false --ignore-not-found=true"
                )
                if cleanup.exit_code != 0:
                    self.log.warning("Namespace cleanup failed for %s: %s", self._namespace, cleanup.stderr)

    def _apply_resourcequota(
        self,
        name: str,
        total_quota: str,
        sc_quota_key: str,
        per_sc_quota: str,
    ) -> bool:
        """Render and apply the ResourceQuota manifest; return True on success."""

        def _mutate(doc: dict[str, Any]) -> dict[str, Any]:
            return _set_resourcequota_fields(
                doc,
                namespace=self._namespace,
                name=name,
                total_quota=total_quota,
                sc_quota_key=sc_quota_key,
                per_sc_quota=per_sc_quota,
            )

        manifest = render_k8s_manifest(_RESOURCEQUOTA_MANIFEST, _mutate)
        returncode, stderr = self._run_kubectl_apply(manifest)
        if returncode != 0:
            self.log.error("kubectl apply failed for ResourceQuota %s: %s", name, stderr)
            return False
        return True

    def _run_per_pvc_usage(
        self,
        *,
        pvc_name: str,
        storage_class: str,
        pvc_request: str,
        rq_name: str,
        sc_quota_key: str,
        bind_timeout: int,
        quota_settle: int,
    ) -> bool:
        """Apply the usage PVC + consumer pod, wait for Bound, and assert per-PVC / quota-used visibility."""
        returncode, stderr = self._apply_pvc(pvc_name, storage_class, "ReadWriteOnce", pvc_request)
        if returncode != 0:
            self.report_subtest(
                "per-pvc-usage",
                passed=False,
                message=f"kubectl apply failed for PVC {pvc_name!r}: {stderr.strip()}",
            )
            return False

        pod_name = f"quota-usage-{uuid.uuid4().hex[:6]}"
        pod_rc, pod_err = _apply_mount_pod_manifest(
            self._kubectl_parts, self._namespace, pod_name, pvc_name, self.timeout
        )
        if pod_rc != 0:
            self.report_subtest(
                "per-pvc-usage",
                passed=False,
                message=f"kubectl apply failed for consumer pod {pod_name!r}: {pod_err.strip()[:200]}",
            )
            return False

        pod_ready, wait_err = _wait_pod_ready(
            self.run_command, self._kubectl_base, self._namespace, pod_name, bind_timeout
        )
        if not pod_ready or not self._wait_pvc_bound(pvc_name, 5):
            self.report_subtest(
                "per-pvc-usage",
                passed=False,
                message=(
                    f"PVC {pvc_name!r} did not reach Bound via consumer pod {pod_name!r} "
                    f"within {bind_timeout}s: {wait_err[:200]}"
                ),
            )
            return False

        capacity = self._get_pvc_capacity(pvc_name)
        if not capacity:
            self.report_subtest(
                "per-pvc-usage",
                passed=False,
                message=f"PVC {pvc_name!r} bound but status.capacity.storage is empty",
            )
            return False

        used = self._wait_quota_section(rq_name, "used", [sc_quota_key, "requests.storage"], quota_settle)
        if used is None:
            self.report_subtest(
                "per-pvc-usage",
                passed=False,
                message=(
                    f"PVC {pvc_name!r} capacity={capacity!r} but ResourceQuota.status.used "
                    f"did not reflect both keys within {quota_settle}s"
                ),
            )
            return False

        self.report_subtest(
            "per-pvc-usage",
            passed=True,
            message=(
                f"PVC {pvc_name!r} capacity={capacity!r}; quota.used["
                f"requests.storage]={used.get('requests.storage')!r}, "
                f"quota.used[{sc_quota_key}]={used.get(sc_quota_key)!r}"
            ),
        )
        return True

    def _run_quota_enforcement(self, pvc_name: str, storage_class: str, request_size: str) -> bool:
        """Attempt to apply an over-quota PVC; pass iff admission rejects with a quota message."""
        returncode, stderr = self._apply_pvc(pvc_name, storage_class, "ReadWriteOnce", request_size)
        if returncode == 0:
            self.report_subtest(
                "quota-enforcement",
                passed=False,
                message=(
                    f"Over-quota PVC {pvc_name!r} (request={request_size}) was admitted; "
                    f"ResourceQuota did not enforce the per-StorageClass cap"
                ),
            )
            return False

        lowered = stderr.lower()
        if any(token in lowered for token in _QUOTA_REJECTION_TOKENS):
            self.report_subtest(
                "quota-enforcement",
                passed=True,
                message=f"Over-quota PVC {pvc_name!r} rejected at admission: {stderr.strip()[:200]}",
            )
            return True

        self.report_subtest(
            "quota-enforcement",
            passed=False,
            message=(
                f"Over-quota PVC {pvc_name!r} apply failed but stderr did not mention quota enforcement: "
                f"{stderr.strip()[:200]}"
            ),
        )
        return False

    def _run_pv_usage_api(self, pvc_name: str) -> bool:
        """Resolve the PVC's bound PV and assert ``spec.capacity/claimRef/csi.driver`` are populated."""
        vol_name_result = self.run_command(
            f"{self._kubectl_base} get pvc {shlex.quote(pvc_name)} "
            f"-n {shlex.quote(self._namespace)} -o jsonpath='{{.spec.volumeName}}'"
        )
        pv_name = vol_name_result.stdout.strip().strip("'")
        if vol_name_result.exit_code != 0 or not pv_name:
            self.report_subtest(
                "pv-usage-api",
                passed=False,
                message=f"Could not resolve volumeName for PVC {pvc_name!r}: {vol_name_result.stderr.strip()}",
            )
            return False

        pv_json = self.run_command(f"{self._kubectl_base} get pv {shlex.quote(pv_name)} -o json")
        if pv_json.exit_code != 0:
            self.report_subtest(
                "pv-usage-api",
                passed=False,
                message=f"kubectl get pv {pv_name!r} failed: {pv_json.stderr.strip()}",
            )
            return False

        try:
            payload = json.loads(pv_json.stdout)
        except json.JSONDecodeError as exc:
            self.report_subtest(
                "pv-usage-api",
                passed=False,
                message=f"Failed to parse PV {pv_name!r} JSON: {exc}",
            )
            return False

        spec = payload.get("spec") or {}
        capacity = (spec.get("capacity") or {}).get("storage")
        claim_ref_name = (spec.get("claimRef") or {}).get("name")
        csi_driver = (spec.get("csi") or {}).get("driver")

        missing: list[str] = []
        if not capacity:
            missing.append("spec.capacity.storage")
        if claim_ref_name != pvc_name:
            missing.append(f"spec.claimRef.name (expected {pvc_name!r}, got {claim_ref_name!r})")
        if not csi_driver:
            missing.append("spec.csi.driver")

        if missing:
            self.report_subtest(
                "pv-usage-api",
                passed=False,
                message=f"PV {pv_name!r} missing required fields: {', '.join(missing)}",
            )
            return False

        self.report_subtest(
            "pv-usage-api",
            passed=True,
            message=(
                f"PV {pv_name!r} spec.capacity.storage={capacity!r}, "
                f"spec.claimRef.name={claim_ref_name!r}, spec.csi.driver={csi_driver!r}"
            ),
        )
        return True

    def _apply_pvc(self, name: str, storage_class: str, access_mode: str, size: str) -> tuple[int, str]:
        """Render the PVC manifest and apply it; return (returncode, stderr)."""

        def _mutate(doc: dict[str, Any]) -> dict[str, Any]:
            return _set_pvc_fields(
                doc, namespace=self._namespace, name=name, sc=storage_class, mode=access_mode, size=size
            )

        manifest = render_k8s_manifest(_PVC_MANIFEST, _mutate)
        return self._run_kubectl_apply(manifest)

    def _run_kubectl_apply(self, manifest: str) -> tuple[int, str]:
        return _apply_manifest(self._kubectl_parts, manifest, self.timeout)

    def _wait_pvc_bound(self, pvc_name: str, timeout_s: int) -> bool:
        return _poll_pvc_bound(self.run_command, self._kubectl_base, self._namespace, pvc_name, timeout_s)

    def _get_pvc_capacity(self, pvc_name: str) -> str:
        """Return ``.status.capacity.storage`` for ``pvc_name`` (empty string if unset)."""
        cmd = (
            f"{self._kubectl_base} get pvc {shlex.quote(pvc_name)} "
            f"-n {shlex.quote(self._namespace)} "
            f"-o jsonpath='{{.status.capacity.storage}}'"
        )
        result = self.run_command(cmd)
        if result.exit_code != 0:
            return ""
        return result.stdout.strip().strip("'")

    def _wait_quota_section(
        self,
        rq_name: str,
        section: str,
        required_keys: list[str],
        timeout_s: int,
    ) -> dict[str, Any] | None:
        """Poll ``ResourceQuota.status.<section>`` until every ``required_keys`` entry appears.

        Returns the section dict once fully populated, or ``None`` on timeout
        / parse failure. Keys are compared verbatim — the caller is
        responsible for passing the concrete per-StorageClass key name.
        """
        deadline = time.time() + timeout_s
        cmd = f"{self._kubectl_base} get resourcequota {shlex.quote(rq_name)} -n {shlex.quote(self._namespace)} -o json"
        while time.time() < deadline:
            result = self.run_command(cmd)
            if result.exit_code == 0 and result.stdout:
                try:
                    payload = json.loads(result.stdout)
                except json.JSONDecodeError:
                    payload = None
                if payload:
                    section_dict = (payload.get("status") or {}).get(section) or {}
                    if all(key in section_dict for key in required_keys):
                        return section_dict
            time.sleep(2.0)
        return None


def _set_resourcequota_fields(
    doc: dict[str, Any],
    *,
    namespace: str,
    name: str,
    total_quota: str,
    sc_quota_key: str,
    per_sc_quota: str,
) -> dict[str, Any]:
    """Mutate a parsed ResourceQuota manifest in place with the requested fields.

    ``spec.hard`` is rebuilt rather than merged so the per-StorageClass key
    (whose name is only known at runtime) fully replaces any placeholder
    value carried by the template.
    """
    metadata = doc.setdefault("metadata", {})
    metadata["name"] = name
    metadata["namespace"] = namespace

    spec = doc.setdefault("spec", {})
    spec["hard"] = {
        "requests.storage": total_quota,
        sc_quota_key: per_sc_quota,
    }
    return doc
