# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

import json
import shlex
from typing import ClassVar

from isvtest.core.k8s import get_kubectl_base_shell
from isvtest.core.validation import BaseValidation


class K8sNodeCountCheck(BaseValidation):
    """Verify the cluster has the expected number of nodes.

    Config keys:
    * ``count`` - exact expected count. Optional when ``min_count`` is set.
    * ``min_count`` - minimum accepted count. Optional when ``count`` is set.
    * ``label_selector`` - optional kubectl selector limiting counted nodes.
    * ``exclude_label_selector`` - optional kubectl selector for nodes to
      subtract from the count. When ``label_selector`` is also set, only nodes
      matching both selectors are subtracted.
    """

    description = "Verify the cluster has the expected number of nodes."
    markers: ClassVar[list[str]] = ["kubernetes"]

    def run(self) -> None:
        expected_count = self.config.get("count")
        min_count = self.config.get("min_count")
        if expected_count is None and min_count is None:
            self.log.info("Skipping: expected count/min_count not configured")
            self.set_passed("Skipped: expected count/min_count not configured")
            return
        if expected_count is not None and min_count is not None:
            self.set_failed("Configure only one of 'count' or 'min_count'")
            return

        expected = self._coerce_non_negative_int(expected_count, "count") if expected_count is not None else None
        minimum = self._coerce_non_negative_int(min_count, "min_count") if min_count is not None else None
        if self._error:
            return

        try:
            label_selector = _optional_selector(self.config.get("label_selector"), "label_selector")
            exclude_selector = _optional_selector(self.config.get("exclude_label_selector"), "exclude_label_selector")
        except ValueError as exc:
            self.set_failed(str(exc))
            return

        node_names = self._get_node_names(label_selector)
        if node_names is None:
            return

        counted_nodes = set(node_names)
        if exclude_selector:
            subtract_selector = _combine_label_selectors(label_selector, exclude_selector)
            excluded_names = self._get_node_names(subtract_selector)
            if excluded_names is None:
                return
            counted_nodes -= set(excluded_names)

        actual_count = len(counted_nodes)
        scope = _scope_description(label_selector, exclude_selector)

        if expected is not None:
            if actual_count != expected:
                self.set_failed(f"Node count mismatch{scope}: expected {expected}, found {actual_count}")
                return
            self.set_passed(f"Node count matched{scope}: {actual_count}")
            return

        if minimum is not None and actual_count < minimum:
            self.set_failed(f"Node count below minimum{scope}: expected at least {minimum}, found {actual_count}")
            return
        self.set_passed(f"Node count matched{scope}: {actual_count} >= {minimum}")

    def _coerce_non_negative_int(self, value: object, field: str) -> int:
        """Coerce config values from YAML/Jinja strings to a non-negative integer."""
        if isinstance(value, bool):
            self.set_failed(f"Invalid {field}: {value!r}")
            return 0
        try:
            parsed = int(value)
        except (ValueError, TypeError):
            self.set_failed(f"Invalid {field}: {value}")
            return 0
        if parsed < 0:
            self.set_failed(f"Invalid {field}: {parsed} (must be >= 0)")
            return 0
        return parsed

    def _get_node_names(self, label_selector: str | None) -> list[str] | None:
        """Return node names matching ``label_selector`` or set failure."""
        selector_args = f" -l {shlex.quote(label_selector)}" if label_selector else ""
        cmd = f"{get_kubectl_base_shell()} get nodes{selector_args} -o name"

        result = self.run_command(cmd)
        if result.exit_code != 0:
            self.set_failed(f"Failed to get node count: {result.stderr}")
            return None

        return _parse_kubectl_name_output(result.stdout)


def _optional_selector(value: object, field: str) -> str | None:
    """Return a stripped label selector or ``None`` for unset/blank values."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Invalid {field}: expected string, got {type(value).__name__}")
    stripped = value.strip()
    return stripped or None


def _combine_label_selectors(*selectors: str | None) -> str | None:
    """Combine label selectors with Kubernetes AND semantics."""
    parts = [selector.strip().strip(",") for selector in selectors if selector and selector.strip().strip(",")]
    return ",".join(parts) if parts else None


def _parse_kubectl_name_output(stdout: str) -> list[str]:
    """Parse ``kubectl get nodes -o name`` output into bare node names."""
    names: list[str] = []
    for line in stdout.splitlines():
        item = line.strip()
        if not item:
            continue
        names.append(item.split("/", 1)[1] if "/" in item else item)
    return names


def _scope_description(label_selector: str | None, exclude_selector: str | None) -> str:
    """Format selector scope for pass/fail messages."""
    parts: list[str] = []
    if label_selector:
        parts.append(f"selector={label_selector!r}")
    if exclude_selector:
        parts.append(f"excluding={exclude_selector!r}")
    return f" ({', '.join(parts)})" if parts else ""


class K8sNodeReadyCheck(BaseValidation):
    description = "Verify all nodes in the cluster are in Ready state."
    markers: ClassVar[list[str]] = ["kubernetes"]

    def run(self) -> None:
        kubectl_base = get_kubectl_base_shell()

        # Use JSON output for safer parsing
        cmd = f"{kubectl_base} get nodes -o json"
        result = self.run_command(cmd)

        if result.exit_code != 0:
            self.set_failed(f"Failed to get nodes: {result.stderr}")
            return

        try:
            nodes_data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            self.set_failed(f"Failed to parse kubectl JSON output: {e}")
            return

        items = nodes_data.get("items", [])
        if not items:
            self.set_passed("No nodes found in cluster")
            return

        not_ready_nodes = []
        total_nodes = len(items)

        for node in items:
            name = node.get("metadata", {}).get("name", "unknown")
            conditions = node.get("status", {}).get("conditions", [])

            # Find the Ready condition
            ready_condition = next((c for c in conditions if c.get("type") == "Ready"), None)

            if not ready_condition:
                not_ready_nodes.append(f"{name} (No Ready condition found)")
                continue

            status = ready_condition.get("status")
            if status != "True":
                reason = ready_condition.get("reason", "Unknown")
                message = ready_condition.get("message", "")
                not_ready_nodes.append(f"{name} (Status: {status}, Reason: {reason} - {message})")

        require_all_ready = self.config.get("require_all_ready", True)

        if not_ready_nodes:
            msg = f"Found {len(not_ready_nodes)} nodes not Ready: {', '.join(not_ready_nodes)}"
            if require_all_ready:
                self.set_failed(msg)
            else:
                self.set_passed(f"WARNING: {msg} (require_all_ready=False)")
            return

        self.set_passed(f"All {total_nodes} nodes are Ready")


class K8sExpectedNodesCheck(BaseValidation):
    description = "Verify all expected nodes from BoM are present in the cluster."
    markers: ClassVar[list[str]] = ["kubernetes"]

    def run(self) -> None:
        expected_names = self.config.get("names", [])
        if not expected_names:
            self.set_passed("Skipped: expected_nodes.names not configured")
            return

        # Get actual nodes
        kubectl_base = get_kubectl_base_shell()
        cmd = f"{kubectl_base} get nodes -o jsonpath='{{.items[*].metadata.name}}'"

        result = self.run_command(cmd)
        if result.exit_code != 0:
            self.set_failed(f"Failed to get nodes: {result.stderr}")
            return

        actual_nodes = result.stdout.strip().split()
        actual_nodes_set = set(actual_nodes)
        expected_names_set = set(expected_names)

        missing_nodes = expected_names_set - actual_nodes_set
        unexpected_nodes = actual_nodes_set - expected_names_set

        errors = []
        if missing_nodes:
            errors.append(f"Missing nodes: {', '.join(sorted(missing_nodes))}")

        if unexpected_nodes:
            allow_unexpected = self.config.get("allow_unexpected_nodes", True)
            if not allow_unexpected:
                errors.append(f"Unexpected nodes: {', '.join(sorted(unexpected_nodes))}")

        if errors:
            self.set_failed("\n".join(errors))
            return

        msg = f"All {len(expected_names)} expected nodes present"
        if unexpected_nodes:
            msg += f" ({len(unexpected_nodes)} unexpected nodes allowed)"
        self.set_passed(msg)
