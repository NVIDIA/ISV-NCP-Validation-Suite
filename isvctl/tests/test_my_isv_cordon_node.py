# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the my-isv BFX01-04 Kubernetes cordon script."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

ISVCTL_ROOT = Path(__file__).resolve().parents[1]
CORDON_SCRIPT = ISVCTL_ROOT / "configs" / "providers" / "my-isv" / "scripts" / "breakfix" / "cordon_node.py"
K8S_CONFIG = ISVCTL_ROOT / "configs" / "providers" / "my-isv" / "config" / "k8s.yaml"


def test_cordon_config_preserves_an_empty_region_argument() -> None:
    """Render an empty region as ``--region=`` instead of a valueless option."""
    config = yaml.safe_load(K8S_CONFIG.read_text())
    steps = config["commands"]["kubernetes"]["steps"]
    cordon_step = next(step for step in steps if step["name"] == "cordon_node")

    assert cordon_step["args"] == ["--region={{region}}"]


def _load_script() -> ModuleType:
    """Load the cordon provider script as a module for direct testing."""
    spec = importlib.util.spec_from_file_location("test_my_isv_cordon_node_script", CORDON_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _completed(
    args: tuple[str, ...], *, payload: dict[str, Any] | None = None, error: str = ""
) -> subprocess.CompletedProcess[str]:
    """Build a completed kubectl command with optional JSON output."""
    return subprocess.CompletedProcess(
        args=["kubectl", *args],
        returncode=1 if error else 0,
        stdout=json.dumps(payload) if payload is not None else "",
        stderr=error,
    )


def _node(*, unschedulable: bool = False) -> dict[str, Any]:
    """Return one Ready, untainted fake node."""
    return {
        "metadata": {"name": "worker-1", "labels": {"kubernetes.io/hostname": "worker-1-host"}},
        "spec": {"unschedulable": unschedulable},
        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
    }


def test_node_taints_are_tolerated_without_bypassing_cordon(monkeypatch: pytest.MonkeyPatch) -> None:
    """Probe pods tolerate the selected GPU taint but never the cordon taint."""
    module = _load_script()
    node = _node()
    node["spec"]["taints"] = [
        {"key": "nvidia.com/gpu", "value": "present", "effect": "NoSchedule"},
        {"key": "node.kubernetes.io/unschedulable", "effect": "NoSchedule"},
    ]
    monkeypatch.setattr(
        module,
        "_run",
        lambda kubectl, *args, **kwargs: _completed(args, payload={"items": [node]}),
    )

    name, hostname, tolerations = module._select_node(["kubectl"], None)

    assert (name, hostname) == ("worker-1", "worker-1-host")
    assert tolerations == [{"key": "nvidia.com/gpu", "operator": "Equal", "value": "present", "effect": "NoSchedule"}]


def _running_pod() -> dict[str, Any]:
    """Return a Ready pod bound to the selected node."""
    return {
        "spec": {"nodeName": "worker-1"},
        "status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "True"}]},
    }


def _unschedulable_pod() -> dict[str, Any]:
    """Return an unbound pod rejected by the scheduler."""
    return {
        "spec": {},
        "status": {
            "phase": "Pending",
            "conditions": [{"type": "PodScheduled", "status": "False", "reason": "Unschedulable"}],
        },
    }


def test_cordon_workflow_proves_all_three_requirements_and_restores_node(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A successful run verifies cordon, old work, and blocked new work before cleanup."""
    module = _load_script()
    calls: list[tuple[str, ...]] = []
    pod_gets = iter([_running_pod(), _unschedulable_pod()])

    def fake_run(kubectl: list[str], *args: str, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        """Return deterministic Kubernetes state for the happy path."""
        calls.append(args)
        if args[:4] == ("get", "nodes", "-o", "json"):
            return _completed(args, payload={"items": [_node()]})
        if args[:3] == ("get", "node", "worker-1"):
            return _completed(args, payload=_node(unschedulable=True))
        if args[:2] == ("get", "pod"):
            return _completed(args, payload=next(pod_gets))
        return _completed(args)

    monkeypatch.setattr(module, "_run", fake_run)
    monkeypatch.setattr(module.uuid, "uuid4", lambda: type("Uuid", (), {"hex": "deadbeefcafebabe"})())
    monkeypatch.setattr(sys, "argv", ["cordon_node.py", "--timeout-seconds", "1"])

    assert module.main() == 0
    result = json.loads(capsys.readouterr().out)

    assert result["success"] is True
    assert result["operation"] == {
        "cordoned": True,
        "new_workloads_blocked": True,
        "existing_workloads_running": True,
        "node_id": "worker-1",
    }
    assert ("cordon", "worker-1") in calls
    assert calls[-1] == ("uncordon", "worker-1")
    assert [call[:3] for call in calls].count(("delete", "pod", "isvtest-bfx-existing-deadbeef")) == 1
    assert [call[:3] for call in calls].count(("delete", "pod", "isvtest-bfx-blocked-deadbeef")) == 1


def test_existing_pod_failure_still_uncordons_and_reports_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A failed continuation check restores schedulability and emits structured failure."""
    module = _load_script()
    calls: list[tuple[str, ...]] = []

    def fake_run(kubectl: list[str], *args: str, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        """Make the existing pod disappear from the selected node after cordon."""
        calls.append(args)
        if args[:4] == ("get", "nodes", "-o", "json"):
            return _completed(args, payload={"items": [_node()]})
        if args[:3] == ("get", "node", "worker-1"):
            return _completed(args, payload=_node(unschedulable=True))
        if args[:2] == ("get", "pod"):
            return _completed(args, payload={"spec": {}, "status": {"phase": "Pending"}})
        return _completed(args)

    monkeypatch.setattr(module, "_run", fake_run)
    monkeypatch.setattr(sys, "argv", ["cordon_node.py", "--timeout-seconds", "1"])

    assert module.main() == 1
    result = json.loads(capsys.readouterr().out)

    assert result["success"] is False
    assert "did not remain Ready" in result["error"]
    assert result["operation"]["existing_workloads_running"] is False
    assert calls[-1] == ("uncordon", "worker-1")


def test_uncordon_failure_cannot_report_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A node left cordoned is a failed test even when all assertions passed."""
    module = _load_script()
    pod_gets = iter([_running_pod(), _unschedulable_pod()])

    def fake_run(kubectl: list[str], *args: str, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        """Pass the workflow but reject the final uncordon."""
        if args[:4] == ("get", "nodes", "-o", "json"):
            return _completed(args, payload={"items": [_node()]})
        if args[:3] == ("get", "node", "worker-1"):
            return _completed(args, payload=_node(unschedulable=True))
        if args[:2] == ("get", "pod"):
            return _completed(args, payload=next(pod_gets))
        if args == ("uncordon", "worker-1"):
            return _completed(args, error="forbidden")
        return _completed(args)

    monkeypatch.setattr(module, "_run", fake_run)
    monkeypatch.setattr(sys, "argv", ["cordon_node.py", "--timeout-seconds", "1"])

    assert module.main() == 1
    result = json.loads(capsys.readouterr().out)

    assert result["success"] is False
    assert result["error"] == "Cordon test cleanup failed"
    assert result["cleanup_errors"] == ["uncordon node worker-1: forbidden"]


def test_requested_precordoned_node_is_rejected_without_uncordoning(monkeypatch: pytest.MonkeyPatch) -> None:
    """The workflow never takes ownership of or restores a node cordoned by someone else."""
    module = _load_script()
    calls: list[tuple[str, ...]] = []

    def fake_run(kubectl: list[str], *args: str, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        """Return only a pre-cordoned requested node."""
        calls.append(args)
        return _completed(args, payload={"items": [_node(unschedulable=True)]})

    monkeypatch.setattr(module, "_run", fake_run)

    with pytest.raises(module.CordonTestError, match="not Ready and schedulable"):
        module._select_node(["kubectl"], "worker-1")
    assert all(call[0] != "uncordon" for call in calls)
