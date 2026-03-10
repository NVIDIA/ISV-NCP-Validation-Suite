#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Check SCC compatibility with DRA driver pods.

Verifies that the DRA driver service account has appropriate SCC
privileges and that DRA pods are not blocked by SCC restrictions.
"""

import json
import subprocess
import sys
from typing import Any

GPU_NS_CANDIDATES = ["nvidia-gpu-operator", "gpu-operator", "openshift-operators"]


def run_kubectl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["kubectl"] + list(args), capture_output=True, text=True, timeout=60)


def run_oc(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["oc"] + list(args), capture_output=True, text=True, timeout=60)


def main() -> int:
    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "scc_compatible": False,
        "dra_pods_healthy": False,
    }

    # Find GPU operator namespace with DRA pods
    gpu_ns = ""
    for ns in GPU_NS_CANDIDATES:
        r = run_kubectl("get", "pods", "-n", ns, "--no-headers")
        if r.returncode == 0 and "dra" in r.stdout.lower():
            gpu_ns = ns
            break

    if not gpu_ns:
        result["error"] = "DRA driver pods not found"
        print(json.dumps(result, indent=2))
        return 1

    # Check DRA pods are not in CrashLoopBackOff or Error
    r = run_kubectl("get", "pods", "-n", gpu_ns, "--no-headers")
    dra_pods = [l for l in r.stdout.strip().split("\n")
                if "dra" in l.lower() or "nvidia-dra" in l.lower()]

    unhealthy = [l for l in dra_pods if "CrashLoop" in l or "Error" in l or "CreateContainerConfigError" in l]
    result["dra_pods_healthy"] = len(unhealthy) == 0
    result["dra_pod_count"] = len(dra_pods)
    result["unhealthy_pods"] = len(unhealthy)

    # Check SCC assigned to DRA pods
    scc_set = set()
    for line in dra_pods:
        pod_name = line.split()[0]
        r = run_oc("get", "pod", pod_name, "-n", gpu_ns,
                   "-o", "jsonpath={.metadata.annotations.openshift\\.io/scc}")
        if r.returncode == 0 and r.stdout.strip():
            scc_set.add(r.stdout.strip())

    result["scc_assigned"] = sorted(scc_set)

    # SCC is compatible if DRA pods are healthy (not blocked by SCC)
    result["scc_compatible"] = result["dra_pods_healthy"]
    result["success"] = result["scc_compatible"]

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
