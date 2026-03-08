#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Check NVIDIA Network Operator is installed and healthy.

Validates the following components:
  - NicClusterPolicy CR exists
  - MOFED driver pods are running in the nvidia-network-operator namespace
  - RDMA shared device plugin pods are running
  - GPU nodes expose rdma/rdma_shared_device_a allocatable resource

Environment:
    NETWORK_OPERATOR_NAMESPACE: Namespace for the operator
        (default: nvidia-network-operator)

Output schema: generic (fields: mofed_ready, mofed_pods,
    rdma_device_plugin_ready, rdma_devices_per_node)
"""

import json
import subprocess
import sys
from typing import Any


def run_cmd(cmd: str, *args: str, **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [cmd] + list(args), capture_output=True, text=True,
        timeout=kwargs.get("timeout", 120),
    )


def main() -> int:
    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "mofed_ready": False,
        "mofed_pods": 0,
        "rdma_device_plugin_ready": False,
        "rdma_devices_per_node": 0,
    }

    try:
        # Check NicClusterPolicy CR exists
        r = run_cmd("kubectl", "get", "nicclusterpolicies.mellanox.com", "-A",
                     "-o", "json")
        if r.returncode != 0:
            result["error"] = (
                "NicClusterPolicy CRD not found. "
                "NVIDIA Network Operator may not be installed."
            )
            print(json.dumps(result, indent=2))
            return 1

        policies = json.loads(r.stdout)
        items = policies.get("items", [])
        if not items:
            result["error"] = "No NicClusterPolicy resources found."
            print(json.dumps(result, indent=2))
            return 1

        print(f"Found {len(items)} NicClusterPolicy resource(s).", file=sys.stderr)

        # Check MOFED driver pods running
        ns = "nvidia-network-operator"
        r = run_cmd("kubectl", "get", "pods", "-n", ns,
                     "-l", "app=mofed",
                     "-o", "json")
        mofed_pods = 0
        if r.returncode == 0:
            pods = json.loads(r.stdout).get("items", [])
            for pod in pods:
                phase = pod.get("status", {}).get("phase", "")
                if phase == "Running":
                    mofed_pods += 1

        # Fallback: search by name pattern if label selector found nothing
        if mofed_pods == 0:
            r = run_cmd("kubectl", "get", "pods", "-n", ns, "-o", "json")
            if r.returncode == 0:
                pods = json.loads(r.stdout).get("items", [])
                for pod in pods:
                    name = pod.get("metadata", {}).get("name", "")
                    phase = pod.get("status", {}).get("phase", "")
                    if "mofed" in name and phase == "Running":
                        mofed_pods += 1

        result["mofed_pods"] = mofed_pods
        result["mofed_ready"] = mofed_pods > 0
        if mofed_pods > 0:
            print(f"MOFED driver pods running: {mofed_pods}", file=sys.stderr)
        else:
            print("No MOFED driver pods found running.", file=sys.stderr)

        # Check RDMA shared device plugin pods
        rdma_dp_ready = False
        r = run_cmd("kubectl", "get", "pods", "-n", ns, "-o", "json")
        if r.returncode == 0:
            pods = json.loads(r.stdout).get("items", [])
            for pod in pods:
                name = pod.get("metadata", {}).get("name", "")
                phase = pod.get("status", {}).get("phase", "")
                if "rdma-shared" in name and phase == "Running":
                    rdma_dp_ready = True
                    break

        result["rdma_device_plugin_ready"] = rdma_dp_ready
        if rdma_dp_ready:
            print("RDMA shared device plugin pods found.", file=sys.stderr)
        else:
            print("No RDMA shared device plugin pods found.", file=sys.stderr)

        # Check rdma/rdma_shared_device_a resource on GPU nodes
        r = run_cmd("kubectl", "get", "nodes", "-o", "json")
        rdma_per_node = 0
        if r.returncode == 0:
            nodes = json.loads(r.stdout).get("items", [])
            for node in nodes:
                allocatable = node.get("status", {}).get("allocatable", {})
                # Check for GPU presence
                gpus = int(allocatable.get("nvidia.com/gpu", "0"))
                if gpus > 0:
                    rdma_count = int(
                        allocatable.get("rdma/rdma_shared_device_a", "0")
                    )
                    if rdma_count > rdma_per_node:
                        rdma_per_node = rdma_count

        result["rdma_devices_per_node"] = rdma_per_node
        if rdma_per_node > 0:
            print(
                f"RDMA devices per GPU node: {rdma_per_node}", file=sys.stderr
            )

        # Success if at least the NicClusterPolicy exists and MOFED is running
        result["success"] = result["mofed_ready"]

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
