# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Unit tests for ``isvtest.validations.k8s_network_policy``."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest

from isvtest.core.runners import CommandResult
from isvtest.validations.k8s_network_policy import (
    K8sDualStackNodeCheck,
    _classify_node,
    _family_summary,
    _is_ipv4,
    _is_ipv6,
    _normalize_require_dual_stack,
)


def _ok(stdout: str = "", stderr: str = "") -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr=stderr, duration=0.0)


def _fail(stdout: str = "", stderr: str = "", exit_code: int = 1) -> CommandResult:
    return CommandResult(exit_code=exit_code, stdout=stdout, stderr=stderr, duration=0.0)


class TestNormalizeRequireDualStack:
    """Tests for ``_normalize_require_dual_stack``."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (True, True),
            (False, False),
            ("true", True),
            ("FALSE", False),
            ("Auto", "auto"),
            ("  auto  ", "auto"),
            ("yes", True),
            ("no", False),
            ("1", True),
            ("0", False),
        ],
    )
    def test_valid_values(self, value: Any, expected: Any) -> None:
        assert _normalize_require_dual_stack(value) == expected

    @pytest.mark.parametrize("value", ["maybe", "", None, 42, object()])
    def test_invalid_values(self, value: Any) -> None:
        with pytest.raises(ValueError):
            _normalize_require_dual_stack(value)


class TestIpClassification:
    """Tests for ``_is_ipv4`` / ``_is_ipv6``."""

    def test_ipv4(self) -> None:
        assert _is_ipv4("10.0.0.1")
        assert not _is_ipv6("10.0.0.1")

    def test_ipv6(self) -> None:
        assert _is_ipv6("fd00::1")
        assert not _is_ipv4("fd00::1")

    def test_invalid(self) -> None:
        assert not _is_ipv4("not-an-ip")
        assert not _is_ipv6("not-an-ip")
        assert not _is_ipv4("")


class TestClassifyNode:
    """Tests for ``_classify_node``."""

    def test_dual_stack_node(self) -> None:
        node = {
            "metadata": {"name": "n1"},
            "status": {
                "addresses": [
                    {"type": "InternalIP", "address": "10.0.0.1"},
                    {"type": "InternalIP", "address": "fd00::1"},
                    {"type": "ExternalIP", "address": "1.2.3.4"},
                ]
            },
        }
        assert _classify_node(node) == (True, True)

    def test_ipv4_only(self) -> None:
        node = {
            "status": {"addresses": [{"type": "InternalIP", "address": "10.0.0.1"}]},
        }
        assert _classify_node(node) == (True, False)

    def test_ipv6_only(self) -> None:
        node = {
            "status": {"addresses": [{"type": "InternalIP", "address": "fd00::1"}]},
        }
        assert _classify_node(node) == (False, True)

    def test_pod_cidrs_supplement_internal_ips(self) -> None:
        # Only IPv4 InternalIP but pod CIDRs expose IPv6 too.
        node = {
            "status": {"addresses": [{"type": "InternalIP", "address": "10.0.0.1"}]},
            "spec": {"podCIDRs": ["10.244.0.0/24", "fd00::/64"]},
        }
        assert _classify_node(node) == (True, True)

    def test_no_addresses(self) -> None:
        assert _classify_node({}) == (False, False)


class TestFamilySummary:
    def test_both(self) -> None:
        assert _family_summary(True, True) == "families=[IPv4, IPv6]"

    def test_none(self) -> None:
        assert _family_summary(False, False) == "families=[none]"


def _nodes_json(node_addrs: list[list[tuple[str, str]]]) -> str:
    """Build a ``kubectl get nodes -o json`` payload.

    ``node_addrs`` is a list of per-node address lists, each element a
    ``(type, address)`` tuple.
    """
    items = []
    for i, addrs in enumerate(node_addrs):
        items.append(
            {
                "metadata": {"name": f"node-{i}"},
                "status": {"addresses": [{"type": t, "address": a} for t, a in addrs]},
            }
        )
    return json.dumps({"items": items})


class TestDualStackNodeCheck:
    """Tests for ``K8sDualStackNodeCheck``."""

    def _make(self, config: dict[str, Any] | None = None) -> K8sDualStackNodeCheck:
        check = K8sDualStackNodeCheck(config=config or {})
        return check

    def test_invalid_require_dual_stack_fails(self) -> None:
        check = self._make({"require_dual_stack": "maybe"})
        with patch.object(check, "run_command") as mock_run:
            check.run()
        mock_run.assert_not_called()
        assert not check.passed
        assert "Invalid require_dual_stack" in check._error

    def test_kubectl_failure_sets_failed(self) -> None:
        check = self._make({"require_dual_stack": True})
        with patch.object(check, "run_command", return_value=_fail(stderr="boom")):
            check.run()
        assert not check.passed
        assert "Failed to list nodes" in check._error

    def test_bad_json_sets_failed(self) -> None:
        check = self._make({"require_dual_stack": True})
        with patch.object(check, "run_command", return_value=_ok(stdout="not-json")):
            check.run()
        assert not check.passed
        assert "parse kubectl JSON" in check._error

    def test_no_nodes_passes(self) -> None:
        check = self._make({"require_dual_stack": True})
        with patch.object(check, "run_command", return_value=_ok(stdout=json.dumps({"items": []}))):
            check.run()
        assert check.passed
        assert "No nodes" in check._output

    def test_require_true_fails_on_single_stack_node(self) -> None:
        payload = _nodes_json(
            [
                [("InternalIP", "10.0.0.1"), ("InternalIP", "fd00::1")],
                [("InternalIP", "10.0.0.2")],  # IPv4 only
            ]
        )
        check = self._make({"require_dual_stack": True})
        with patch.object(check, "run_command", return_value=_ok(stdout=payload)):
            check.run()
        assert not check.passed
        assert "node-1" in check._error

    def test_require_true_passes_when_all_dual_stack(self) -> None:
        payload = _nodes_json(
            [
                [("InternalIP", "10.0.0.1"), ("InternalIP", "fd00::1")],
                [("InternalIP", "10.0.0.2"), ("InternalIP", "fd00::2")],
            ]
        )
        check = self._make({"require_dual_stack": True})
        with patch.object(check, "run_command", return_value=_ok(stdout=payload)):
            check.run()
        assert check.passed
        assert "All 2 nodes" in check._output

    def test_require_false_always_passes(self) -> None:
        payload = _nodes_json([[("InternalIP", "10.0.0.1")]])
        check = self._make({"require_dual_stack": False})
        with patch.object(check, "run_command", return_value=_ok(stdout=payload)):
            check.run()
        assert check.passed
        assert "Informational" in check._output

    def test_auto_skips_when_no_node_dual_stack(self) -> None:
        payload = _nodes_json(
            [
                [("InternalIP", "10.0.0.1")],
                [("InternalIP", "10.0.0.2")],
            ]
        )
        check = self._make({"require_dual_stack": "auto"})
        with patch.object(check, "run_command", return_value=_ok(stdout=payload)):
            check.run()
        assert check.passed
        assert "single-stack" in check._output

    def test_auto_requires_all_when_any_node_dual_stack(self) -> None:
        payload = _nodes_json(
            [
                [("InternalIP", "10.0.0.1"), ("InternalIP", "fd00::1")],
                [("InternalIP", "10.0.0.2")],  # Missing IPv6
            ]
        )
        check = self._make({"require_dual_stack": "auto"})
        with patch.object(check, "run_command", return_value=_ok(stdout=payload)):
            check.run()
        assert not check.passed
        assert "node-1" in check._error

    def test_auto_passes_when_all_nodes_dual_stack(self) -> None:
        payload = _nodes_json(
            [
                [("InternalIP", "10.0.0.1"), ("InternalIP", "fd00::1")],
                [("InternalIP", "10.0.0.2"), ("InternalIP", "fd00::2")],
            ]
        )
        check = self._make({"require_dual_stack": "auto"})
        with patch.object(check, "run_command", return_value=_ok(stdout=payload)):
            check.run()
        assert check.passed
        assert "All 2 nodes" in check._output
