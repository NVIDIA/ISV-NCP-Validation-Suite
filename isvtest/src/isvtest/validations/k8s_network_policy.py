# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Dual-stack node validation (K8S22).

This module provides :class:`K8sDualStackNodeCheck`, which inspects every
node's ``InternalIP`` addresses (and ``spec.podCIDRs`` as a supplementary
hint) and verifies that the cluster is dual-stack (IPv4 + IPv6) when
configuration requires it.
"""

from __future__ import annotations

import ipaddress
import json
from typing import Any, ClassVar

from isvtest.config.settings import get_k8s_require_dual_stack
from isvtest.core.k8s import get_kubectl_base_shell
from isvtest.core.validation import BaseValidation


class K8sDualStackNodeCheck(BaseValidation):
    """Verify that cluster nodes have both IPv4 and IPv6 InternalIP addresses.

    Config keys (with defaults):
        require_dual_stack: One of ``True``, ``False``, or ``"auto"``. Defaults
            to the value returned by
            :func:`isvtest.config.settings.get_k8s_require_dual_stack`
            (``"auto"`` unless ``K8S_REQUIRE_DUAL_STACK`` is set).

    Decision matrix:
        * ``True`` — any node missing either family fails the validation.
        * ``False`` — always passes; per-node summary is still emitted.
        * ``"auto"`` — if at least one node has both families the cluster is
          treated as dual-stack and every node must be; if no node has both
          the check skips.
    """

    description: ClassVar[str] = "Verify IPv4 and IPv6 addresses on dual-stack nodes."
    timeout: ClassVar[int] = 60
    markers: ClassVar[list[str]] = ["kubernetes"]

    def run(self) -> None:
        require_dual_stack = self.config.get("require_dual_stack", get_k8s_require_dual_stack())
        try:
            normalized = _normalize_require_dual_stack(require_dual_stack)
        except ValueError:
            self.set_failed(
                f"Invalid require_dual_stack value: {require_dual_stack!r} (expected True, False, or 'auto')"
            )
            return

        result = self.run_command(f"{get_kubectl_base_shell()} get nodes -o json")
        if result.exit_code != 0:
            self.set_failed(f"Failed to list nodes: {result.stderr}")
            return

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            self.set_failed(f"Failed to parse kubectl JSON output: {exc}")
            return

        nodes = payload.get("items", [])
        if not nodes:
            self.set_passed("No nodes found in cluster")
            return

        node_families: list[tuple[str, bool, bool]] = []
        for node in nodes:
            name = node.get("metadata", {}).get("name", "unknown")
            has_v4, has_v6 = _classify_node(node)
            node_families.append((name, has_v4, has_v6))

        cluster_has_dual_stack_node = any(v4 and v6 for _, v4, v6 in node_families)

        if normalized == "auto" and not cluster_has_dual_stack_node:
            # Still emit per-node subtests for visibility, then skip.
            for name, has_v4, has_v6 in node_families:
                self.report_subtest(
                    f"node/{name}",
                    passed=True,
                    message=_family_summary(has_v4, has_v6),
                    skipped=True,
                )
            self.set_passed("Skipped: cluster is single-stack (auto mode)")
            return

        require_both = normalized is True or (normalized == "auto" and cluster_has_dual_stack_node)
        failures: list[str] = []

        for name, has_v4, has_v6 in node_families:
            summary = _family_summary(has_v4, has_v6)
            if require_both:
                node_ok = has_v4 and has_v6
                self.report_subtest(f"node/{name}", passed=node_ok, message=summary)
                if not node_ok:
                    failures.append(f"{name} ({summary})")
            else:
                self.report_subtest(f"node/{name}", passed=True, message=summary)

        if failures:
            self.set_failed(f"{len(failures)} node(s) missing required address family: {', '.join(failures)}")
            return

        if require_both:
            self.set_passed(f"All {len(node_families)} nodes have IPv4 and IPv6 InternalIPs")
        else:
            self.set_passed(
                f"Informational: per-node IPv4/IPv6 summary recorded for "
                f"{len(node_families)} node(s) (require_dual_stack=False)"
            )


def _normalize_require_dual_stack(value: object) -> bool | str:
    """Normalize a ``require_dual_stack`` config value.

    Returns ``True``, ``False``, or ``"auto"``. Raises ``ValueError`` for
    anything else.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
        if lowered == "auto":
            return "auto"
    raise ValueError(f"unrecognized require_dual_stack value: {value!r}")


def _is_ipv4(addr: str) -> bool:
    """Return True iff ``addr`` parses as an IPv4 address."""
    try:
        return isinstance(ipaddress.ip_address(addr), ipaddress.IPv4Address)
    except ValueError:
        return False


def _is_ipv6(addr: str) -> bool:
    """Return True iff ``addr`` parses as an IPv6 address."""
    try:
        return isinstance(ipaddress.ip_address(addr), ipaddress.IPv6Address)
    except ValueError:
        return False


def _classify_node(node: dict[str, Any]) -> tuple[bool, bool]:
    """Return ``(has_ipv4, has_ipv6)`` for a node based on InternalIP and podCIDRs."""
    has_v4 = False
    has_v6 = False

    for addr in node.get("status", {}).get("addresses", []) or []:
        if addr.get("type") != "InternalIP":
            continue
        ip_str = addr.get("address", "")
        if _is_ipv4(ip_str):
            has_v4 = True
        elif _is_ipv6(ip_str):
            has_v6 = True

    # Also inspect podCIDRs as a supplementary hint — helpful on clusters that
    # assign only one InternalIP family but allocate both pod CIDR families.
    for cidr in node.get("spec", {}).get("podCIDRs", []) or []:
        try:
            network = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            continue
        if isinstance(network, ipaddress.IPv4Network):
            has_v4 = True
        elif isinstance(network, ipaddress.IPv6Network):
            has_v6 = True

    return has_v4, has_v6


def _family_summary(has_v4: bool, has_v6: bool) -> str:
    """Human-readable per-node family summary."""
    families = []
    if has_v4:
        families.append("IPv4")
    if has_v6:
        families.append("IPv6")
    return f"families=[{', '.join(families) or 'none'}]"
