# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Unit tests for ``isvtest.validations.k8s_storage``."""

from __future__ import annotations

import json
import subprocess
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from isvtest.core.runners import CommandResult
from isvtest.validations.k8s_storage import (
    K8sCsiStorageQuotaApiCheck,
    K8sCsiStorageTypesCheck,
    _set_pvc_fields,
    _set_resourcequota_fields,
)


def _ok(stdout: str = "", stderr: str = "") -> CommandResult:
    """Return a successful ``CommandResult`` with the given stdout/stderr."""
    return CommandResult(exit_code=0, stdout=stdout, stderr=stderr, duration=0.0)


def _fail(stdout: str = "", stderr: str = "", exit_code: int = 1) -> CommandResult:
    """Return a failing ``CommandResult`` with the given output and exit code."""
    return CommandResult(exit_code=exit_code, stdout=stdout, stderr=stderr, duration=0.0)


class _FakeProc:
    """Minimal stand-in for ``subprocess.CompletedProcess`` used by ``kubectl apply``."""

    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _FakeClock:
    """Tiny fake clock — advances on each ``sleep`` call.

    Used to keep poll loops from burning real wall-clock time under mocked
    ``run_command`` / ``subprocess.run``: without it, patching only ``time.sleep``
    makes the deadline-based loops spin for ``timeout_s`` seconds of real time.
    Patch both ``time.sleep`` and ``time.time`` onto this instance's methods.
    """

    def __init__(self, start: float = 0.0) -> None:
        self._now = float(start)

    def time(self) -> float:
        return self._now

    def sleep(self, seconds: float) -> None:
        self._now += float(seconds)


@contextmanager
def _patched_clock() -> Any:
    """Patch ``k8s_storage.time.sleep`` and ``k8s_storage.time.time`` with a ``_FakeClock``.

    Without patching ``time.time`` as well, deadline-based poll loops would
    spin for ``timeout_s`` seconds of real wall clock even when ``sleep`` is
    a no-op. Using a single fake clock for both keeps the tests in-process
    and deterministic.
    """
    clock = _FakeClock()
    with (
        patch("isvtest.validations.k8s_storage.time.sleep", side_effect=clock.sleep),
        patch("isvtest.validations.k8s_storage.time.time", side_effect=clock.time),
    ):
        yield clock


class TestSetPvcFields:
    """Tests for ``_set_pvc_fields`` — the in-memory manifest mutator."""

    def _base_doc(self) -> dict[str, Any]:
        return {
            "apiVersion": "v1",
            "kind": "PersistentVolumeClaim",
            "metadata": {"name": "placeholder", "namespace": "placeholder"},
            "spec": {
                "accessModes": ["ReadWriteOnce"],
                "resources": {"requests": {"storage": "1Gi"}},
                "storageClassName": "placeholder",
            },
        }

    def test_overrides_all_fields(self) -> None:
        doc = self._base_doc()
        out = _set_pvc_fields(doc, namespace="ns1", name="p1", sc="gp3", mode="ReadWriteMany", size="5Gi")
        assert out["metadata"]["namespace"] == "ns1"
        assert out["metadata"]["name"] == "p1"
        assert out["spec"]["storageClassName"] == "gp3"
        assert out["spec"]["accessModes"] == ["ReadWriteMany"]
        assert out["spec"]["resources"]["requests"]["storage"] == "5Gi"

    def test_mutation_is_in_place(self) -> None:
        doc = self._base_doc()
        out = _set_pvc_fields(doc, namespace="ns", name="p", sc="sc", mode="ReadWriteOnce", size="1Gi")
        assert out is doc

    def test_missing_sections_are_created(self) -> None:
        out = _set_pvc_fields({}, namespace="ns", name="p", sc="sc", mode="ReadWriteOnce", size="1Gi")
        assert out["metadata"]["namespace"] == "ns"
        assert out["spec"]["storageClassName"] == "sc"
        assert out["spec"]["resources"]["requests"]["storage"] == "1Gi"


class TestK8sCsiStorageTypesCheck:
    """Tests for ``K8sCsiStorageTypesCheck``."""

    def _make(self, config: dict[str, Any] | None = None) -> K8sCsiStorageTypesCheck:
        return K8sCsiStorageTypesCheck(config=config or {})

    def _stub_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Isolate from developer env: never leak a StorageClass from the host.
        for var in ("K8S_CSI_BLOCK_SC", "K8S_CSI_SHARED_FS_SC", "K8S_CSI_NFS_SC"):
            monkeypatch.delenv(var, raising=False)

    def test_no_storage_classes_configured_skips_without_work(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._stub_env(monkeypatch)
        check = self._make({})
        with patch.object(check, "run_command") as mock_run:
            check.run()
        mock_run.assert_not_called()
        assert check.passed
        assert "Skipped" in check._output
        assert "no StorageClass" in check._output

    def test_all_configured_storage_classes_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._stub_env(monkeypatch)
        check = self._make(
            {
                "block_storage_class": "gp3",
                "shared_fs_storage_class": "efs-sc",
                "nfs_storage_class": "efs-sc",
                "bind_timeout_s": 5,
                "namespace_prefix": "ut",
            }
        )

        def fake_run(cmd: str, timeout: int | None = None) -> CommandResult:
            if "create namespace" in cmd:
                return _ok()
            if "get storageclass" in cmd:
                return _ok(stdout="storageclass.storage.k8s.io/x\n")
            if "wait --for=condition=Ready" in cmd:
                return _ok()
            if "get pvc" in cmd:
                return _ok(stdout="Bound")
            if "delete namespace" in cmd:
                return _ok()
            raise AssertionError(f"unexpected command: {cmd}")

        with (
            patch.object(check, "run_command", side_effect=fake_run),
            patch("isvtest.validations.k8s_storage.subprocess.run", return_value=_FakeProc(returncode=0)),
            _patched_clock(),
        ):
            check.run()

        assert check.passed, check._error
        outcomes = {r["name"]: r for r in check._subtest_results}
        for t in ("block", "shared-fs", "nfs"):
            assert outcomes[f"sc-exists[{t}]"]["passed"]
            assert outcomes[f"pvc-binds[{t}]"]["passed"]

    def test_only_block_configured_skips_others(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._stub_env(monkeypatch)
        check = self._make(
            {
                "block_storage_class": "gp3",
                "bind_timeout_s": 5,
                "namespace_prefix": "ut",
            }
        )

        def fake_run(cmd: str, timeout: int | None = None) -> CommandResult:
            if "create namespace" in cmd:
                return _ok()
            if "get storageclass" in cmd:
                return _ok(stdout="storageclass.storage.k8s.io/gp3\n")
            if "wait --for=condition=Ready" in cmd:
                return _ok()
            if "get pvc" in cmd:
                return _ok(stdout="Bound")
            if "delete namespace" in cmd:
                return _ok()
            raise AssertionError(f"unexpected command: {cmd}")

        with (
            patch.object(check, "run_command", side_effect=fake_run),
            patch("isvtest.validations.k8s_storage.subprocess.run", return_value=_FakeProc(returncode=0)),
            _patched_clock(),
        ):
            check.run()

        assert check.passed
        outcomes = {r["name"]: r for r in check._subtest_results}
        assert outcomes["sc-exists[block]"]["passed"] and not outcomes["sc-exists[block]"]["skipped"]
        assert outcomes["pvc-binds[block]"]["passed"] and not outcomes["pvc-binds[block]"]["skipped"]
        for t in ("shared-fs", "nfs"):
            assert outcomes[f"sc-exists[{t}]"]["skipped"]
            assert outcomes[f"pvc-binds[{t}]"]["skipped"]

    def test_missing_storageclass_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._stub_env(monkeypatch)
        check = self._make({"block_storage_class": "nope", "bind_timeout_s": 5, "namespace_prefix": "ut"})

        def fake_run(cmd: str, timeout: int | None = None) -> CommandResult:
            if "create namespace" in cmd:
                return _ok()
            if "get storageclass" in cmd:
                return _fail(stderr='Error from server (NotFound): storageclasses.storage.k8s.io "nope" not found')
            if "delete namespace" in cmd:
                return _ok()
            raise AssertionError(f"unexpected command: {cmd}")

        with (
            patch.object(check, "run_command", side_effect=fake_run),
            _patched_clock(),
        ):
            check.run()

        assert not check.passed
        outcomes = {r["name"]: r for r in check._subtest_results}
        assert not outcomes["sc-exists[block]"]["passed"]
        # Paired PVC subtest must be marked skipped so the failure isn't double-counted.
        assert outcomes["pvc-binds[block]"]["skipped"]

    def test_pvc_never_binds_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._stub_env(monkeypatch)
        check = self._make({"block_storage_class": "gp3", "bind_timeout_s": 1, "namespace_prefix": "ut"})

        def fake_run(cmd: str, timeout: int | None = None) -> CommandResult:
            if "create namespace" in cmd:
                return _ok()
            if "get storageclass" in cmd:
                return _ok(stdout="storageclass.storage.k8s.io/gp3\n")
            # Consumer pod never reaches Ready because the PVC stays Pending
            # under WaitForFirstConsumer with no provisioner available.
            if "wait --for=condition=Ready" in cmd:
                return _fail(stderr="timed out waiting for the condition")
            if "get pvc" in cmd:
                return _ok(stdout="Pending")
            if "delete namespace" in cmd:
                return _ok()
            raise AssertionError(f"unexpected command: {cmd}")

        with (
            patch.object(check, "run_command", side_effect=fake_run),
            patch("isvtest.validations.k8s_storage.subprocess.run", return_value=_FakeProc(returncode=0)),
            _patched_clock(),
        ):
            check.run()

        assert not check.passed
        outcomes = {r["name"]: r for r in check._subtest_results}
        assert outcomes["sc-exists[block]"]["passed"]
        assert not outcomes["pvc-binds[block]"]["passed"]
        assert "did not reach Bound" in outcomes["pvc-binds[block]"]["message"]

    def test_pvc_apply_failure_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._stub_env(monkeypatch)
        check = self._make({"block_storage_class": "gp3", "bind_timeout_s": 5, "namespace_prefix": "ut"})

        def fake_run(cmd: str, timeout: int | None = None) -> CommandResult:
            if "create namespace" in cmd:
                return _ok()
            if "get storageclass" in cmd:
                return _ok(stdout="storageclass.storage.k8s.io/gp3\n")
            if "delete namespace" in cmd:
                return _ok()
            raise AssertionError(f"unexpected command: {cmd}")

        with (
            patch.object(check, "run_command", side_effect=fake_run),
            patch(
                "isvtest.validations.k8s_storage.subprocess.run",
                return_value=_FakeProc(returncode=1, stderr="admission denied"),
            ),
            _patched_clock(),
        ):
            check.run()

        assert not check.passed
        outcomes = {r["name"]: r for r in check._subtest_results}
        assert not outcomes["pvc-binds[block]"]["passed"]
        assert "kubectl apply failed" in outcomes["pvc-binds[block]"]["message"]

    def test_kubectl_apply_timeout_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._stub_env(monkeypatch)
        check = self._make({"block_storage_class": "gp3", "bind_timeout_s": 5, "namespace_prefix": "ut"})

        def fake_run(cmd: str, timeout: int | None = None) -> CommandResult:
            if "create namespace" in cmd:
                return _ok()
            if "get storageclass" in cmd:
                return _ok(stdout="storageclass.storage.k8s.io/gp3\n")
            if "delete namespace" in cmd:
                return _ok()
            raise AssertionError(f"unexpected command: {cmd}")

        with (
            patch.object(check, "run_command", side_effect=fake_run),
            patch(
                "isvtest.validations.k8s_storage.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="kubectl", timeout=1),
            ),
            _patched_clock(),
        ):
            check.run()

        assert not check.passed
        outcomes = {r["name"]: r for r in check._subtest_results}
        assert not outcomes["pvc-binds[block]"]["passed"]

    def test_namespace_create_failure_sets_failed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._stub_env(monkeypatch)
        check = self._make({"block_storage_class": "gp3"})

        def fake_run(cmd: str, timeout: int | None = None) -> CommandResult:
            if "create namespace" in cmd:
                return _fail(stderr="forbidden")
            raise AssertionError(f"unexpected command: {cmd}")

        with patch.object(check, "run_command", side_effect=fake_run):
            check.run()

        assert not check.passed
        assert "Failed to create namespace" in check._error

    def test_env_fallback_is_honoured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._stub_env(monkeypatch)
        monkeypatch.setenv("K8S_CSI_BLOCK_SC", "gp3-from-env")
        check = self._make({"bind_timeout_s": 5, "namespace_prefix": "ut"})

        seen: list[str] = []

        def fake_run(cmd: str, timeout: int | None = None) -> CommandResult:
            seen.append(cmd)
            if "create namespace" in cmd:
                return _ok()
            if "get storageclass" in cmd:
                return _ok(stdout="storageclass.storage.k8s.io/gp3-from-env\n")
            if "wait --for=condition=Ready" in cmd:
                return _ok()
            if "get pvc" in cmd:
                return _ok(stdout="Bound")
            if "delete namespace" in cmd:
                return _ok()
            raise AssertionError(f"unexpected command: {cmd}")

        with (
            patch.object(check, "run_command", side_effect=fake_run),
            patch("isvtest.validations.k8s_storage.subprocess.run", return_value=_FakeProc(returncode=0)),
            _patched_clock(),
        ):
            check.run()

        assert check.passed
        assert any("gp3-from-env" in c for c in seen)

    def test_rendered_manifest_is_valid_yaml_with_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """End-to-end check that the applied manifest parses and carries the expected fields."""
        self._stub_env(monkeypatch)
        check = self._make(
            {
                "shared_fs_storage_class": "efs-sc",
                "pvc_size": "3Gi",
                "bind_timeout_s": 5,
                "namespace_prefix": "ut",
            }
        )

        captured: list[str] = []

        def fake_run(cmd: str, timeout: int | None = None) -> CommandResult:
            if "create namespace" in cmd:
                return _ok()
            if "get storageclass" in cmd:
                return _ok(stdout="storageclass.storage.k8s.io/efs-sc\n")
            if "wait --for=condition=Ready" in cmd:
                return _ok()
            if "get pvc" in cmd:
                return _ok(stdout="Bound")
            if "delete namespace" in cmd:
                return _ok()
            raise AssertionError(f"unexpected command: {cmd}")

        def capture_apply(cmd: list[str], **kwargs: Any) -> _FakeProc:
            captured.append(kwargs.get("input", ""))
            return _FakeProc(returncode=0)

        with (
            patch.object(check, "run_command", side_effect=fake_run),
            patch("isvtest.validations.k8s_storage.subprocess.run", side_effect=capture_apply),
            _patched_clock(),
        ):
            check.run()

        assert check.passed
        # Two applies per storage type (PVC, mount pod); find the PVC doc.
        all_docs = [d for rendered in captured for d in yaml.safe_load_all(rendered) if d]
        pvcs = [d for d in all_docs if d.get("kind") == "PersistentVolumeClaim"]
        assert len(pvcs) == 1, f"expected exactly one rendered PVC, got {len(pvcs)}"
        pvc = pvcs[0]
        assert pvc["spec"]["storageClassName"] == "efs-sc"
        assert pvc["spec"]["accessModes"] == ["ReadWriteMany"]
        assert pvc["spec"]["resources"]["requests"]["storage"] == "3Gi"
        assert pvc["metadata"]["namespace"].startswith("ut-")


class TestSetResourceQuotaFields:
    """Tests for ``_set_resourcequota_fields`` — the in-memory manifest mutator."""

    def _base_doc(self) -> dict[str, Any]:
        return {
            "apiVersion": "v1",
            "kind": "ResourceQuota",
            "metadata": {"name": "placeholder", "namespace": "placeholder"},
            "spec": {"hard": {"requests.storage": "10Gi"}},
        }

    def test_overrides_all_fields(self) -> None:
        doc = self._base_doc()
        out = _set_resourcequota_fields(
            doc,
            namespace="ns1",
            name="rq1",
            total_quota="20Gi",
            sc_quota_key="gp3.storageclass.storage.k8s.io/requests.storage",
            per_sc_quota="5Gi",
        )
        assert out["metadata"]["namespace"] == "ns1"
        assert out["metadata"]["name"] == "rq1"
        assert out["spec"]["hard"] == {
            "requests.storage": "20Gi",
            "gp3.storageclass.storage.k8s.io/requests.storage": "5Gi",
        }

    def test_mutation_is_in_place(self) -> None:
        doc = self._base_doc()
        out = _set_resourcequota_fields(
            doc,
            namespace="ns",
            name="rq",
            total_quota="10Gi",
            sc_quota_key="sc.storageclass.storage.k8s.io/requests.storage",
            per_sc_quota="5Gi",
        )
        assert out is doc

    def test_hard_replaces_placeholder(self) -> None:
        """The mutator must *replace* spec.hard rather than merge so placeholder keys don't leak."""
        doc = self._base_doc()
        # Add a stale key that must be dropped.
        doc["spec"]["hard"]["legacy.storageclass.storage.k8s.io/requests.storage"] = "1Gi"
        out = _set_resourcequota_fields(
            doc,
            namespace="ns",
            name="rq",
            total_quota="10Gi",
            sc_quota_key="gp3.storageclass.storage.k8s.io/requests.storage",
            per_sc_quota="5Gi",
        )
        assert "legacy.storageclass.storage.k8s.io/requests.storage" not in out["spec"]["hard"]


class TestK8sCsiStorageQuotaApiCheck:
    """Tests for ``K8sCsiStorageQuotaApiCheck``."""

    def _make(self, config: dict[str, Any] | None = None) -> K8sCsiStorageQuotaApiCheck:
        return K8sCsiStorageQuotaApiCheck(config=config or {})

    def _stub_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Isolate from developer env: never leak a StorageClass from the host.
        for var in ("K8S_CSI_BLOCK_SC", "K8S_CSI_SHARED_FS_SC", "K8S_CSI_NFS_SC"):
            monkeypatch.delenv(var, raising=False)

    def _happy_config(self) -> dict[str, Any]:
        return {
            "storage_class": "gp3",
            "total_quota": "10Gi",
            "per_sc_quota": "5Gi",
            "pvc_request": "1Gi",
            "over_quota_request": "100Gi",
            "bind_timeout_s": 5,
            "quota_settle_s": 5,
            "namespace_prefix": "ut",
        }

    def _quota_json(
        self,
        *,
        sc_key: str,
        hard: dict[str, str] | None,
        used: dict[str, str] | None,
    ) -> str:
        """Build a ``kubectl get resourcequota -o json`` payload with the given status sections."""
        status: dict[str, Any] = {}
        if hard is not None:
            status["hard"] = hard
        if used is not None:
            status["used"] = used
        return json.dumps({"metadata": {"name": "rq"}, "status": status})

    def _pv_json(
        self,
        *,
        claim_ref_name: str = "usage-pvc",
        capacity: str | None = "1Gi",
        csi_driver: str | None = "ebs.csi.aws.com",
    ) -> str:
        """Build a ``kubectl get pv -o json`` payload with tunable fields."""
        spec: dict[str, Any] = {}
        if capacity is not None:
            spec["capacity"] = {"storage": capacity}
        spec["claimRef"] = {"name": claim_ref_name}
        if csi_driver is not None:
            spec["csi"] = {"driver": csi_driver}
        return json.dumps({"kind": "PersistentVolume", "spec": spec})

    @staticmethod
    def _kind_from_input(manifest_yaml: str) -> str:
        """Peek at the first non-empty doc of a manifest and return its ``kind``."""
        for doc in yaml.safe_load_all(manifest_yaml):
            if doc:
                return str(doc.get("kind", ""))
        return ""

    def _apply_router(
        self,
        *,
        rq_rc: int = 0,
        rq_err: str = "",
        usage_rc: int = 0,
        usage_err: str = "",
        over_rc: int = 1,
        over_err: str = 'error: persistentvolumeclaims "foo" is forbidden: exceeded quota',
    ) -> Any:
        """Return a ``subprocess.run`` side_effect that routes by manifest kind/name.

        The happy path returns success for ResourceQuota and usage-PVC apply and
        a forbidden/exceeded-quota rejection for the over-quota PVC apply. Any
        knob can be tweaked to simulate a specific failure.
        """

        def _route(cmd: list[str], **kwargs: Any) -> _FakeProc:
            manifest = kwargs.get("input", "") or ""
            kind = self._kind_from_input(manifest)
            if kind == "ResourceQuota":
                return _FakeProc(returncode=rq_rc, stderr=rq_err)
            if kind == "Pod":
                # Consumer pod applied alongside the usage PVC so Bound can
                # happen under WaitForFirstConsumer. Success by default.
                return _FakeProc(returncode=0)
            if kind == "PersistentVolumeClaim":
                # The usage PVC is applied before the over-quota PVC, so track order.
                # We distinguish by name via the metadata. The over-quota PVC name
                # starts with "quota-over-"; usage PVC name starts with "quota-usage-".
                for doc in yaml.safe_load_all(manifest):
                    if not doc:
                        continue
                    name = doc.get("metadata", {}).get("name", "")
                    if name.startswith("quota-over-"):
                        return _FakeProc(returncode=over_rc, stderr=over_err)
                    return _FakeProc(returncode=usage_rc, stderr=usage_err)
            raise AssertionError(f"unexpected manifest kind={kind!r}")

        return _route

    def _run_command_router(
        self,
        *,
        quota_hard: dict[str, str] | None,
        quota_used: dict[str, str] | None,
        pvc_phase: str = "Bound",
        pvc_capacity: str = "1Gi",
        volume_name: str = "pv-123",
        pv_payload: str | None = None,
        sc_key: str = "gp3.storageclass.storage.k8s.io/requests.storage",
    ) -> Any:
        """Build a ``run_command`` side_effect that answers every query the check issues."""
        pv_json = pv_payload if pv_payload is not None else self._pv_json()

        def _route(cmd: str, timeout: int | None = None) -> CommandResult:
            if "create namespace" in cmd:
                return _ok()
            if "get resourcequota" in cmd and "-o json" in cmd:
                return _ok(stdout=self._quota_json(sc_key=sc_key, hard=quota_hard, used=quota_used))
            if "wait --for=condition=Ready" in cmd:
                # Consumer pod reaches Ready whenever the PVC phase is Bound;
                # when the PVC stays Pending, the wait fails so the check
                # reports the timeout correctly.
                return _ok() if pvc_phase == "Bound" else _fail(stderr="timed out waiting for the condition")
            if "get pvc" in cmd and "jsonpath='{.status.phase}'" in cmd:
                return _ok(stdout=pvc_phase)
            if "get pvc" in cmd and "jsonpath='{.status.capacity.storage}'" in cmd:
                return _ok(stdout=pvc_capacity)
            if "get pvc" in cmd and "jsonpath='{.spec.volumeName}'" in cmd:
                return _ok(stdout=volume_name)
            if "get pv " in cmd and "-o json" in cmd:
                return _ok(stdout=pv_json)
            if "delete namespace" in cmd:
                return _ok()
            raise AssertionError(f"unexpected command: {cmd}")

        return _route

    # ----- tests -----

    def test_no_storage_class_configured_skips_without_work(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._stub_env(monkeypatch)
        check = self._make({})
        with patch.object(check, "run_command") as mock_run:
            check.run()
        mock_run.assert_not_called()
        assert check.passed
        assert "Skipped" in check._output

    def test_happy_path_all_subtests_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._stub_env(monkeypatch)
        check = self._make(self._happy_config())
        sc_key = "gp3.storageclass.storage.k8s.io/requests.storage"
        run = self._run_command_router(
            quota_hard={"requests.storage": "10Gi", sc_key: "5Gi"},
            quota_used={"requests.storage": "1Gi", sc_key: "1Gi"},
            pv_payload=self._pv_json(),
        )

        # run_command_router's _pv_json defaults claim_ref_name to "usage-pvc" but
        # the real PVC name is generated with a UUID prefix. Patch accordingly.
        def _run_with_dynamic_pvname(cmd: str, timeout: int | None = None) -> CommandResult:
            if "get pv " in cmd and "-o json" in cmd:
                # Resolve the current usage PVC name so spec.claimRef.name matches.
                return _ok(stdout=self._pv_json(claim_ref_name=getattr(check, "_usage_pvc_name", "usage-pvc")))
            return run(cmd, timeout)

        # Capture the usage PVC name during subprocess.run (ResourceQuota is applied
        # first, then usage PVC, then consumer Pod, then over-quota PVC).
        def _capture_apply(cmd: list[str], **kwargs: Any) -> _FakeProc:
            manifest = kwargs.get("input", "") or ""
            kind = self._kind_from_input(manifest)
            if kind == "PersistentVolumeClaim":
                for doc in yaml.safe_load_all(manifest):
                    if not doc:
                        continue
                    name = doc.get("metadata", {}).get("name", "")
                    if name.startswith("quota-usage-"):
                        check._usage_pvc_name = name  # type: ignore[attr-defined]
                        return _FakeProc(returncode=0)
                    if name.startswith("quota-over-"):
                        return _FakeProc(returncode=1, stderr="forbidden: exceeded quota")
            if kind == "ResourceQuota":
                return _FakeProc(returncode=0)
            if kind == "Pod":
                return _FakeProc(returncode=0)
            raise AssertionError(f"unexpected manifest kind={kind!r}")

        with (
            patch.object(check, "run_command", side_effect=_run_with_dynamic_pvname),
            patch("isvtest.validations.k8s_storage.subprocess.run", side_effect=_capture_apply),
            _patched_clock(),
        ):
            check.run()

        assert check.passed, check._error
        outcomes = {r["name"]: r for r in check._subtest_results}
        for name in ("resourcequota-storage-api", "per-pvc-usage", "quota-enforcement", "pv-usage-api"):
            assert outcomes[name]["passed"], f"{name}: {outcomes[name]['message']}"
            assert not outcomes[name]["skipped"]

    def test_resourcequota_apply_failure_skips_dependents(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._stub_env(monkeypatch)
        check = self._make(self._happy_config())
        run = self._run_command_router(quota_hard=None, quota_used=None)

        with (
            patch.object(check, "run_command", side_effect=run),
            patch(
                "isvtest.validations.k8s_storage.subprocess.run",
                side_effect=self._apply_router(rq_rc=1, rq_err="admission denied"),
            ),
            _patched_clock(),
        ):
            check.run()

        assert not check.passed
        outcomes = {r["name"]: r for r in check._subtest_results}
        assert not outcomes["resourcequota-storage-api"]["passed"]
        for dependent in ("per-pvc-usage", "quota-enforcement", "pv-usage-api"):
            assert outcomes[dependent]["skipped"]

    def test_resourcequota_hard_never_populates_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._stub_env(monkeypatch)
        check = self._make(self._happy_config())
        # Apply succeeds, but .status.hard is never published.
        run = self._run_command_router(quota_hard=None, quota_used=None)

        with (
            patch.object(check, "run_command", side_effect=run),
            patch(
                "isvtest.validations.k8s_storage.subprocess.run",
                side_effect=self._apply_router(),
            ),
            _patched_clock(),
        ):
            check.run()

        assert not check.passed
        outcomes = {r["name"]: r for r in check._subtest_results}
        assert not outcomes["resourcequota-storage-api"]["passed"]
        assert outcomes["per-pvc-usage"]["skipped"]

    def test_usage_pvc_apply_failure_fails_per_pvc_usage(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._stub_env(monkeypatch)
        check = self._make(self._happy_config())
        sc_key = "gp3.storageclass.storage.k8s.io/requests.storage"
        run = self._run_command_router(
            quota_hard={"requests.storage": "10Gi", sc_key: "5Gi"},
            quota_used=None,
        )

        with (
            patch.object(check, "run_command", side_effect=run),
            patch(
                "isvtest.validations.k8s_storage.subprocess.run",
                side_effect=self._apply_router(usage_rc=1, usage_err="boom"),
            ),
            _patched_clock(),
        ):
            check.run()

        assert not check.passed
        outcomes = {r["name"]: r for r in check._subtest_results}
        assert outcomes["resourcequota-storage-api"]["passed"]
        assert not outcomes["per-pvc-usage"]["passed"]
        # pv-usage-api depends on a bound usage PVC; should be skipped.
        assert outcomes["pv-usage-api"]["skipped"]

    def test_usage_pvc_never_binds_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._stub_env(monkeypatch)
        check = self._make(self._happy_config())
        sc_key = "gp3.storageclass.storage.k8s.io/requests.storage"
        run = self._run_command_router(
            quota_hard={"requests.storage": "10Gi", sc_key: "5Gi"},
            quota_used=None,
            pvc_phase="Pending",
        )

        with (
            patch.object(check, "run_command", side_effect=run),
            patch("isvtest.validations.k8s_storage.subprocess.run", side_effect=self._apply_router()),
            _patched_clock(),
        ):
            check.run()

        assert not check.passed
        outcomes = {r["name"]: r for r in check._subtest_results}
        assert not outcomes["per-pvc-usage"]["passed"]
        assert "did not reach Bound" in outcomes["per-pvc-usage"]["message"]

    def test_quota_used_never_reflects_usage_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._stub_env(monkeypatch)
        check = self._make(self._happy_config())
        sc_key = "gp3.storageclass.storage.k8s.io/requests.storage"
        # hard is populated but used never includes the per-SC key.
        run = self._run_command_router(
            quota_hard={"requests.storage": "10Gi", sc_key: "5Gi"},
            quota_used={"requests.storage": "1Gi"},  # missing per-SC entry
        )

        with (
            patch.object(check, "run_command", side_effect=run),
            patch("isvtest.validations.k8s_storage.subprocess.run", side_effect=self._apply_router()),
            _patched_clock(),
        ):
            check.run()

        assert not check.passed
        outcomes = {r["name"]: r for r in check._subtest_results}
        assert outcomes["resourcequota-storage-api"]["passed"]
        assert not outcomes["per-pvc-usage"]["passed"]
        assert "did not reflect" in outcomes["per-pvc-usage"]["message"]

    def test_over_quota_pvc_admitted_fails_enforcement(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._stub_env(monkeypatch)
        check = self._make(self._happy_config())
        sc_key = "gp3.storageclass.storage.k8s.io/requests.storage"
        run = self._run_command_router(
            quota_hard={"requests.storage": "10Gi", sc_key: "5Gi"},
            quota_used={"requests.storage": "1Gi", sc_key: "1Gi"},
        )
        # Over-quota PVC incorrectly succeeds (returncode 0).
        with (
            patch.object(check, "run_command", side_effect=run),
            patch(
                "isvtest.validations.k8s_storage.subprocess.run",
                side_effect=self._apply_router(over_rc=0, over_err=""),
            ),
            _patched_clock(),
        ):
            check.run()

        assert not check.passed
        outcomes = {r["name"]: r for r in check._subtest_results}
        assert not outcomes["quota-enforcement"]["passed"]
        assert "admitted" in outcomes["quota-enforcement"]["message"]

    def test_over_quota_pvc_rejected_without_quota_message_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._stub_env(monkeypatch)
        check = self._make(self._happy_config())
        sc_key = "gp3.storageclass.storage.k8s.io/requests.storage"
        run = self._run_command_router(
            quota_hard={"requests.storage": "10Gi", sc_key: "5Gi"},
            quota_used={"requests.storage": "1Gi", sc_key: "1Gi"},
        )
        with (
            patch.object(check, "run_command", side_effect=run),
            patch(
                "isvtest.validations.k8s_storage.subprocess.run",
                side_effect=self._apply_router(over_rc=1, over_err="network error"),
            ),
            _patched_clock(),
        ):
            check.run()

        assert not check.passed
        outcomes = {r["name"]: r for r in check._subtest_results}
        assert not outcomes["quota-enforcement"]["passed"]
        assert "did not mention quota" in outcomes["quota-enforcement"]["message"]

    @pytest.mark.parametrize(
        ("mutator_kwargs", "expected_missing"),
        [
            ({"csi_driver": None}, "spec.csi.driver"),
            ({"capacity": None}, "spec.capacity.storage"),
            ({"claim_ref_name": "other-pvc"}, "spec.claimRef.name"),
        ],
    )
    def test_pv_usage_api_detects_missing_fields(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mutator_kwargs: dict[str, Any],
        expected_missing: str,
    ) -> None:
        self._stub_env(monkeypatch)
        check = self._make(self._happy_config())
        sc_key = "gp3.storageclass.storage.k8s.io/requests.storage"

        # We need the PV's claimRef.name to match the generated usage-PVC name on
        # the "happy" cases. To keep the parametrisation simple we let the check
        # record the usage name during apply, then rebuild the PV payload against
        # it when responding to `get pv ... -o json`.
        usage_name_holder: dict[str, str] = {}

        def _apply_side_effect(cmd: list[str], **kwargs: Any) -> _FakeProc:
            manifest = kwargs.get("input", "") or ""
            kind = self._kind_from_input(manifest)
            if kind == "ResourceQuota":
                return _FakeProc(returncode=0)
            if kind == "Pod":
                return _FakeProc(returncode=0)
            if kind == "PersistentVolumeClaim":
                for doc in yaml.safe_load_all(manifest):
                    if not doc:
                        continue
                    name = doc.get("metadata", {}).get("name", "")
                    if name.startswith("quota-usage-"):
                        usage_name_holder["name"] = name
                        return _FakeProc(returncode=0)
                    if name.startswith("quota-over-"):
                        return _FakeProc(returncode=1, stderr="forbidden: exceeded quota")
            raise AssertionError(f"unexpected kind={kind!r}")

        def _run(cmd: str, timeout: int | None = None) -> CommandResult:
            if "create namespace" in cmd:
                return _ok()
            if "get resourcequota" in cmd:
                return _ok(
                    stdout=self._quota_json(
                        sc_key=sc_key,
                        hard={"requests.storage": "10Gi", sc_key: "5Gi"},
                        used={"requests.storage": "1Gi", sc_key: "1Gi"},
                    )
                )
            if "wait --for=condition=Ready" in cmd:
                return _ok()
            if "get pvc" in cmd and "status.phase" in cmd:
                return _ok(stdout="Bound")
            if "get pvc" in cmd and "status.capacity.storage" in cmd:
                return _ok(stdout="1Gi")
            if "get pvc" in cmd and "spec.volumeName" in cmd:
                return _ok(stdout="pv-123")
            if "get pv " in cmd and "-o json" in cmd:
                # Build PV payload; default claim ref matches usage PVC unless
                # overridden by mutator_kwargs.
                claim_name = mutator_kwargs.get("claim_ref_name", usage_name_holder.get("name", "usage-pvc"))
                capacity = mutator_kwargs.get("capacity", "1Gi") if "capacity" in mutator_kwargs else "1Gi"
                csi_driver = (
                    mutator_kwargs.get("csi_driver", "ebs.csi.aws.com")
                    if "csi_driver" in mutator_kwargs
                    else "ebs.csi.aws.com"
                )
                return _ok(
                    stdout=self._pv_json(
                        claim_ref_name=claim_name,
                        capacity=capacity,
                        csi_driver=csi_driver,
                    )
                )
            if "delete namespace" in cmd:
                return _ok()
            raise AssertionError(f"unexpected command: {cmd}")

        with (
            patch.object(check, "run_command", side_effect=_run),
            patch("isvtest.validations.k8s_storage.subprocess.run", side_effect=_apply_side_effect),
            _patched_clock(),
        ):
            check.run()

        assert not check.passed
        outcomes = {r["name"]: r for r in check._subtest_results}
        assert not outcomes["pv-usage-api"]["passed"]
        assert expected_missing in outcomes["pv-usage-api"]["message"]

    def test_env_fallback_is_honoured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._stub_env(monkeypatch)
        monkeypatch.setenv("K8S_CSI_BLOCK_SC", "gp3-from-env")
        sc_key = "gp3-from-env.storageclass.storage.k8s.io/requests.storage"
        # Drop storage_class so env has to provide it.
        cfg = self._happy_config()
        cfg.pop("storage_class")
        check = self._make(cfg)

        usage_name_holder: dict[str, str] = {}

        def _apply(cmd: list[str], **kwargs: Any) -> _FakeProc:
            manifest = kwargs.get("input", "") or ""
            kind = self._kind_from_input(manifest)
            if kind == "ResourceQuota":
                # Verify the per-SC key inside the ResourceQuota references the env SC.
                for doc in yaml.safe_load_all(manifest):
                    if not doc:
                        continue
                    assert sc_key in doc["spec"]["hard"]
                return _FakeProc(returncode=0)
            if kind == "Pod":
                return _FakeProc(returncode=0)
            if kind == "PersistentVolumeClaim":
                for doc in yaml.safe_load_all(manifest):
                    if not doc:
                        continue
                    name = doc.get("metadata", {}).get("name", "")
                    if name.startswith("quota-usage-"):
                        usage_name_holder["name"] = name
                        assert doc["spec"]["storageClassName"] == "gp3-from-env"
                        return _FakeProc(returncode=0)
                    if name.startswith("quota-over-"):
                        return _FakeProc(returncode=1, stderr="forbidden: exceeded quota")
            raise AssertionError(f"unexpected kind={kind!r}")

        def _run(cmd: str, timeout: int | None = None) -> CommandResult:
            if "create namespace" in cmd:
                return _ok()
            if "get resourcequota" in cmd:
                return _ok(
                    stdout=self._quota_json(
                        sc_key=sc_key,
                        hard={"requests.storage": "10Gi", sc_key: "5Gi"},
                        used={"requests.storage": "1Gi", sc_key: "1Gi"},
                    )
                )
            if "wait --for=condition=Ready" in cmd:
                return _ok()
            if "get pvc" in cmd and "status.phase" in cmd:
                return _ok(stdout="Bound")
            if "get pvc" in cmd and "status.capacity.storage" in cmd:
                return _ok(stdout="1Gi")
            if "get pvc" in cmd and "spec.volumeName" in cmd:
                return _ok(stdout="pv-env")
            if "get pv " in cmd:
                return _ok(
                    stdout=self._pv_json(
                        claim_ref_name=usage_name_holder.get("name", "usage-pvc"),
                    )
                )
            if "delete namespace" in cmd:
                return _ok()
            raise AssertionError(f"unexpected command: {cmd}")

        with (
            patch.object(check, "run_command", side_effect=_run),
            patch("isvtest.validations.k8s_storage.subprocess.run", side_effect=_apply),
            _patched_clock(),
        ):
            check.run()

        assert check.passed, check._error

    def test_namespace_create_failure_sets_failed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._stub_env(monkeypatch)
        check = self._make({"storage_class": "gp3"})

        def _run(cmd: str, timeout: int | None = None) -> CommandResult:
            if "create namespace" in cmd:
                return _fail(stderr="forbidden")
            raise AssertionError(f"unexpected command: {cmd}")

        with patch.object(check, "run_command", side_effect=_run):
            check.run()

        assert not check.passed
        assert "Failed to create namespace" in check._error

    def test_rendered_resourcequota_manifest_is_valid_yaml(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """End-to-end check that the applied ResourceQuota carries the expected keys."""
        self._stub_env(monkeypatch)
        check = self._make(self._happy_config())
        sc_key = "gp3.storageclass.storage.k8s.io/requests.storage"

        captured: dict[str, str] = {}
        usage_name_holder: dict[str, str] = {}

        def _apply(cmd: list[str], **kwargs: Any) -> _FakeProc:
            manifest = kwargs.get("input", "") or ""
            kind = self._kind_from_input(manifest)
            if kind == "ResourceQuota":
                captured["rq"] = manifest
                return _FakeProc(returncode=0)
            if kind == "Pod":
                return _FakeProc(returncode=0)
            if kind == "PersistentVolumeClaim":
                for doc in yaml.safe_load_all(manifest):
                    if not doc:
                        continue
                    name = doc.get("metadata", {}).get("name", "")
                    if name.startswith("quota-usage-"):
                        usage_name_holder["name"] = name
                        return _FakeProc(returncode=0)
                    if name.startswith("quota-over-"):
                        return _FakeProc(returncode=1, stderr="forbidden: exceeded quota")
            raise AssertionError(f"unexpected kind={kind!r}")

        run = self._run_command_router(
            quota_hard={"requests.storage": "10Gi", sc_key: "5Gi"},
            quota_used={"requests.storage": "1Gi", sc_key: "1Gi"},
        )

        def _run_with_dynamic_pvname(cmd: str, timeout: int | None = None) -> CommandResult:
            if "get pv " in cmd and "-o json" in cmd:
                return _ok(stdout=self._pv_json(claim_ref_name=usage_name_holder.get("name", "usage-pvc")))
            return run(cmd, timeout)

        with (
            patch.object(check, "run_command", side_effect=_run_with_dynamic_pvname),
            patch("isvtest.validations.k8s_storage.subprocess.run", side_effect=_apply),
            _patched_clock(),
        ):
            check.run()

        assert check.passed, check._error
        rq_yaml = captured["rq"]
        docs = [d for d in yaml.safe_load_all(rq_yaml) if d]
        assert len(docs) == 1
        rq = docs[0]
        assert rq["kind"] == "ResourceQuota"
        assert rq["metadata"]["namespace"].startswith("ut-")
        assert rq["spec"]["hard"] == {"requests.storage": "10Gi", sc_key: "5Gi"}
