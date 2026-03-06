# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Cluster-related validations for step outputs.

Validations for Kubernetes clusters, GPU operators, and performance benchmarks.
"""

from typing import ClassVar

from isvtest.core.validation import BaseValidation


class NodeCountCheck(BaseValidation):
    """Validate that the cluster has the expected number of nodes.

    Config:
        step_output: The step output to check
        expected: Expected node count (required)

    Step output:
        node_count: Actual node count
    """

    description: ClassVar[str] = "Check cluster node count matches expected"
    markers: ClassVar[list[str]] = []

    def run(self) -> None:
        step_output = self.config.get("step_output", {})
        expected = self.config.get("expected")

        if expected is None:
            self.set_failed("Missing 'expected' parameter")
            return

        actual = step_output.get("node_count")
        if actual is None:
            self.set_failed("No 'node_count' in step output")
            return

        if actual == expected:
            self.set_passed(f"Node count matches: {actual}")
        else:
            self.set_failed(f"Node count mismatch: expected {expected}, got {actual}")


class ClusterHealthCheck(BaseValidation):
    """Validate that the cluster is healthy and accessible.

    Config:
        step_output: The step output to check

    Step output:
        cluster_name: Cluster name (required)
        endpoint: Optional cluster endpoint
        node_count: Should be > 0
    """

    description: ClassVar[str] = "Check cluster is healthy"
    markers: ClassVar[list[str]] = []

    def run(self) -> None:
        step_output = self.config.get("step_output", {})

        cluster_name = step_output.get("cluster_name")
        if not cluster_name:
            self.set_failed("No 'cluster_name' in step output")
            return

        node_count = step_output.get("node_count", 0)
        if node_count <= 0:
            self.set_failed(f"Cluster {cluster_name} has no nodes")
            return

        endpoint = step_output.get("endpoint", "N/A")
        self.set_passed(f"Cluster {cluster_name} healthy: {node_count} nodes, endpoint: {endpoint}")


class GpuOperatorInstalledCheck(BaseValidation):
    """Validate that GPU operator is installed.

    Config:
        step_output: The step output to check

    Step output:
        installed: Boolean indicating installation status
        driver_version: Optional driver version
        gpu_count: Optional GPU count
    """

    description: ClassVar[str] = "Check GPU operator installation"
    markers: ClassVar[list[str]] = ["gpu"]

    def run(self) -> None:
        step_output = self.config.get("step_output", {})

        installed = step_output.get("installed")
        if installed is None:
            self.set_failed("No 'installed' field in step output")
            return

        if not installed:
            self.set_failed("GPU operator not installed")
            return

        driver_version = step_output.get("driver_version", "unknown")
        gpu_count = step_output.get("gpu_count", "unknown")
        self.set_passed(f"GPU operator installed: driver={driver_version}, gpus={gpu_count}")


class PerformanceCheck(BaseValidation):
    """Validate workload performance metrics.

    Config:
        step_output: The step output to check
        min_bandwidth_gbps: Minimum required bandwidth (optional)
        max_latency_ms: Maximum allowed latency (optional)

    Step output:
        metrics: Dictionary with performance metrics
    """

    description: ClassVar[str] = "Check workload performance meets requirements"
    markers: ClassVar[list[str]] = ["workload"]

    def run(self) -> None:
        step_output = self.config.get("step_output", {})
        metrics = step_output.get("metrics", {})

        min_bandwidth = self.config.get("min_bandwidth_gbps")
        max_latency = self.config.get("max_latency_ms")

        if not min_bandwidth and not max_latency:
            self.set_failed("No performance thresholds specified (min_bandwidth_gbps or max_latency_ms)")
            return

        failures = []

        if min_bandwidth:
            actual_bandwidth = metrics.get("bandwidth_gbps", metrics.get("bandwidth"))
            if actual_bandwidth is None:
                failures.append("No bandwidth metric found")
            elif actual_bandwidth < min_bandwidth:
                failures.append(f"Bandwidth {actual_bandwidth} Gbps < required {min_bandwidth} Gbps")

        if max_latency:
            actual_latency = metrics.get("latency_ms", metrics.get("latency"))
            if actual_latency is None:
                failures.append("No latency metric found")
            elif actual_latency > max_latency:
                failures.append(f"Latency {actual_latency}ms > max allowed {max_latency}ms")

        if failures:
            self.set_failed("; ".join(failures))
        else:
            self.set_passed(f"Performance OK: metrics={metrics}")
