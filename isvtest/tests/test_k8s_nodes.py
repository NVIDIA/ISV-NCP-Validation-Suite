# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Unit tests for ``isvtest.validations.k8s_nodes``."""

from __future__ import annotations

from unittest.mock import patch

from isvtest.core.runners import CommandResult, Runner
from isvtest.validations.k8s_nodes import (
    K8sNodeCountCheck,
    _combine_label_selectors,
    _parse_kubectl_name_output,
)


def _ok(stdout: str = "", stderr: str = "") -> CommandResult:
    """Return a successful ``CommandResult`` with the given stdout/stderr."""
    return CommandResult(exit_code=0, stdout=stdout, stderr=stderr, duration=0.0)


def _fail(stderr: str = "boom") -> CommandResult:
    """Return a failing ``CommandResult``."""
    return CommandResult(exit_code=1, stdout="", stderr=stderr, duration=0.0)


class StubRunner(Runner):
    """Runner that returns preloaded command results and records commands."""

    def __init__(self, responses: list[CommandResult]) -> None:
        self.responses = list(responses)
        self.commands: list[str | list[str]] = []

    def run(self, cmd: str | list[str], timeout: int = 60) -> CommandResult:
        self.commands.append(cmd)
        return self.responses.pop(0)


def _run_check(config: dict[str, object], responses: list[CommandResult]) -> tuple[dict[str, object], StubRunner]:
    runner = StubRunner(responses)
    check = K8sNodeCountCheck(runner=runner, config=config)
    with patch("isvtest.validations.k8s_nodes.get_kubectl_base_shell", return_value="kubectl"):
        result = check.execute()
    return result, runner


def test_parse_kubectl_name_output_strips_kind_prefix() -> None:
    """Verify _parse_kubectl_name_output strips the 'kind/' prefix from names."""
    assert _parse_kubectl_name_output("node/base-1\nnode/base-2\n\n") == ["base-1", "base-2"]


def test_combine_label_selectors_uses_and_semantics() -> None:
    """Verify label selectors are combined with Kubernetes AND semantics."""
    assert _combine_label_selectors("role=gpu", "pool=test") == "role=gpu,pool=test"


def test_node_count_exact_count_passes() -> None:
    """Verify an exact node count match passes."""
    result, runner = _run_check({"count": 2}, [_ok("node/base-1\nnode/base-2\n")])

    assert result["passed"] is True
    assert result["output"] == "Node count matched: 2"
    assert runner.commands == ["kubectl get nodes -o name"]


def test_node_count_with_label_selector_counts_scoped_nodes() -> None:
    """Verify node counting honors the configured label selector."""
    result, runner = _run_check(
        {"count": 1, "label_selector": "nvidia.com/gpu.present=true"},
        [_ok("node/gpu-1\n")],
    )

    assert result["passed"] is True
    assert runner.commands == ["kubectl get nodes -l nvidia.com/gpu.present=true -o name"]


def test_node_count_excludes_matching_nodes() -> None:
    """Verify node counting excludes nodes that match the exclusion selector."""
    result, runner = _run_check(
        {"count": 2, "exclude_label_selector": "isv.ncp.validation/workload=data-ingest"},
        [
            _ok("node/base-1\nnode/base-2\nnode/test-1\nnode/test-2\n"),
            _ok("node/test-1\nnode/test-2\n"),
        ],
    )

    assert result["passed"] is True
    assert result["output"] == "Node count matched (excluding='isv.ncp.validation/workload=data-ingest'): 2"
    assert runner.commands == [
        "kubectl get nodes -o name",
        "kubectl get nodes -l isv.ncp.validation/workload=data-ingest -o name",
    ]


def test_exclusion_is_intersected_with_label_selector() -> None:
    """Verify exclusion selectors are scoped by the primary label selector."""
    result, runner = _run_check(
        {
            "count": 1,
            "label_selector": "node-role.kubernetes.io/worker=true",
            "exclude_label_selector": "pool=test",
        },
        [
            _ok("node/worker-1\nnode/test-1\n"),
            _ok("node/test-1\n"),
        ],
    )

    assert result["passed"] is True
    assert runner.commands == [
        "kubectl get nodes -l node-role.kubernetes.io/worker=true -o name",
        "kubectl get nodes -l node-role.kubernetes.io/worker=true,pool=test -o name",
    ]


def test_node_count_min_count_passes_when_actual_is_higher() -> None:
    """Verify min_count passes when the actual node count is higher."""
    result, _runner = _run_check({"min_count": 2}, [_ok("node/base-1\nnode/base-2\nnode/extra\n")])

    assert result["passed"] is True
    assert result["output"] == "Node count matched: 3 >= 2"


def test_node_count_mismatch_fails() -> None:
    """Verify mismatched exact node counts fail with a clear error."""
    result, _runner = _run_check({"count": 3}, [_ok("node/base-1\nnode/base-2\n")])

    assert result["passed"] is False
    assert result["error"] == "Node count mismatch: expected 3, found 2"


def test_node_count_fails_when_kubectl_fails() -> None:
    """Verify kubectl failures are reported as node count failures."""
    result, _runner = _run_check({"count": 1}, [_fail("cluster unavailable")])

    assert result["passed"] is False
    assert result["error"] == "Failed to get node count: cluster unavailable"


def test_node_count_rejects_count_and_min_count_together() -> None:
    """Verify count and min_count cannot be configured together."""
    result, _runner = _run_check({"count": 1, "min_count": 1}, [])

    assert result["passed"] is False
    assert result["error"] == "Configure only one of 'count' or 'min_count'"
