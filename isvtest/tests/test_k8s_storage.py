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

import subprocess
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from isvtest.core.runners import CommandResult
from isvtest.validations.k8s_storage import (
    K8sCsiStorageTypesCheck,
    _set_pvc_fields,
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
            patch("isvtest.validations.k8s_storage.time.sleep"),
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
            patch("isvtest.validations.k8s_storage.time.sleep"),
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
            patch("isvtest.validations.k8s_storage.time.sleep"),
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
            patch("isvtest.validations.k8s_storage.time.sleep"),
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
            patch("isvtest.validations.k8s_storage.time.sleep"),
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
            patch("isvtest.validations.k8s_storage.time.sleep"),
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
            patch("isvtest.validations.k8s_storage.time.sleep"),
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
            patch("isvtest.validations.k8s_storage.time.sleep"),
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
