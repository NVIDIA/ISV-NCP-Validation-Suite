# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

import shlex
from typing import ClassVar

from isvtest.core.k8s import get_kubectl_command
from isvtest.core.validation import BaseValidation


class K8sGpuLabelsCheck(BaseValidation):
    description = "Verify GPU nodes have proper NVIDIA labels."
    markers: ClassVar[list[str]] = ["kubernetes", "gpu"]

    def run(self) -> None:
        label_selector = self.config.get("label_selector", "nvidia.com/gpu.present=true")

        kubectl_parts = get_kubectl_command()
        kubectl_base = " ".join(shlex.quote(part) for part in kubectl_parts)

        cmd = f"{kubectl_base} get nodes -l {shlex.quote(label_selector)} --no-headers"
        result = self.run_command(cmd)

        if result.exit_code != 0:
            self.set_failed(f"Failed to query GPU nodes: {result.stderr}")
            return

        nodes = [line for line in result.stdout.splitlines() if line.strip()]
        if not nodes:
            self.set_failed(f"No GPU nodes found with label '{label_selector}'")
            return

        self.set_passed(f"Found {len(nodes)} nodes with label '{label_selector}'")


class K8sGpuCapacityCheck(BaseValidation):
    """Check GPU capacity at the node level by querying Kubernetes resources.

    This check queries node capacity directly via kubectl, providing accurate
    GPU counts without the limitations of pod-level resource isolation.

    Config options:
        resource_name: Resource name to check (default: nvidia.com/gpu)
        expected_total: Expected total GPU count across all nodes (optional)
        expected_per_node: Expected GPU count per GPU node (optional)
    """

    description = "Verify node GPU capacity matches expected counts."
    markers: ClassVar[list[str]] = ["kubernetes", "gpu"]

    def run(self) -> None:
        resource_name = self.config.get("resource_name", "nvidia.com/gpu")
        expected_total = self.config.get("expected_total")
        expected_per_node = self.config.get("expected_per_node")

        # Convert to int for Jinja2 templated values
        try:
            if expected_total is not None:
                expected_total = int(expected_total)
            if expected_per_node is not None:
                expected_per_node = int(expected_per_node)
        except (TypeError, ValueError):
            self.set_failed(
                f"Invalid expected GPU capacity values: "
                f"expected_total={expected_total!r}, expected_per_node={expected_per_node!r}"
            )
            return

        # Need to escape dot for jsonpath if it exists (e.g. nvidia.com/gpu -> nvidia\.com/gpu)
        escaped_resource = resource_name.replace(".", "\\.")

        kubectl_parts = get_kubectl_command()
        kubectl_base = " ".join(shlex.quote(part) for part in kubectl_parts)

        # Check for resource in node capacity
        cmd = f'{kubectl_base} get nodes -o jsonpath=\'{{range .items[*]}}{{.metadata.name}}{{"\\t"}}{{.status.capacity.{escaped_resource}}}{{"\\n"}}{{end}}\''
        result = self.run_command(cmd)

        if result.exit_code != 0:
            self.set_failed(f"Failed to get node capacity: {result.stderr}")
            return

        gpu_nodes_count = 0
        total_gpus = 0
        per_node_mismatches = []

        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) >= 2 and parts[1].strip():
                try:
                    # Handle "1" or "1Gi" (though GPU resources usually purely numeric)
                    val_str = parts[1]
                    if val_str.isdigit():
                        count = int(val_str)
                        if count > 0:
                            gpu_nodes_count += 1
                            total_gpus += count
                            # Check per-node count if configured
                            if expected_per_node is not None and count != expected_per_node:
                                node_name = parts[0]
                                per_node_mismatches.append(f"{node_name} ({count} != {expected_per_node})")
                except ValueError:
                    pass

        if gpu_nodes_count == 0:
            self.set_failed(f"No '{resource_name}' resources found in node capacity")
            return

        # Check per-node count
        if per_node_mismatches:
            self.set_failed(f"GPU count mismatch on nodes: {', '.join(per_node_mismatches)}")
            return

        # Check total count
        if expected_total is not None and total_gpus != expected_total:
            self.set_failed(f"Total GPU count mismatch: found {total_gpus}, expected {expected_total}")
            return

        self.set_passed(f"Found {total_gpus} total '{resource_name}' across {gpu_nodes_count} nodes")
