#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Verify GPU Operator DRA driver is healthy.

Checks that the DRA driver DaemonSet pods are running and
the ResourceClass for GPUs exists.
"""

import json
import subprocess
import sys
from typing import Any

GPU_NS_CANDIDATES = ["nvidia-gpu-operator", "gpu-operator", "openshift-operators"]


def run_kubectl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["kubectl"] + list(args), capture_output=True, text=True, timeout=60)


def main() -> int:
    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "driver_ready": False,
        "resource_class_exists": False,
        "pods_ready": 0,
        "pods_desired": 0,
    }

    # Find DRA driver pods
    gpu_ns = ""
    for ns in GPU_NS_CANDIDATES:
        r = run_kubectl("get", "pods", "-n", ns, "--no-headers")
        if r.returncode == 0 and "dra-driver" in r.stdout.lower():
            gpu_ns = ns
            break

    if not gpu_ns:
        result["error"] = "DRA driver pods not found — is GPU Operator in DRA mode?"
        print(json.dumps(result, indent=2))
        return 1

    result["namespace"] = gpu_ns

    # Count DRA driver pods
    r = run_kubectl("get", "pods", "-n", gpu_ns, "--no-headers")
    dra_pods = [l for l in r.stdout.strip().split("\n")
                if "dra-driver" in l.lower() or "nvidia-dra" in l.lower()]
    running = sum(1 for l in dra_pods if "Running" in l)
    result["pods_ready"] = running
    result["pods_desired"] = len(dra_pods)
    result["driver_ready"] = running > 0

    # Check ResourceClass
    r = run_kubectl("get", "resourceclass", "--no-headers")
    if r.returncode == 0:
        for line in r.stdout.strip().split("\n"):
            if "gpu" in line.lower() or "nvidia" in line.lower():
                result["resource_class_exists"] = True
                result["resource_class_name"] = line.split()[0]
                break

    # Check DRA feature gate
    r = run_kubectl("get", "featuregate", "cluster", "-o",
                    "jsonpath={.spec.featureSet}")
    result["feature_set"] = r.stdout.strip() if r.returncode == 0 else "Unknown"

    result["success"] = result["driver_ready"] and result["resource_class_exists"]

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
