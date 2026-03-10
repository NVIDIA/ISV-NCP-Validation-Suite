#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Validate DCGM metrics content by scraping a DCGM exporter pod."""

import json
import subprocess
import sys
from typing import Any

GPU_NS_CANDIDATES = ["nvidia-gpu-operator", "gpu-operator", "openshift-operators"]
EXPECTED_METRICS = [
    "DCGM_FI_DEV_GPU_UTIL",
    "DCGM_FI_DEV_MEM_COPY_UTIL",
    "DCGM_FI_DEV_GPU_TEMP",
    "DCGM_FI_DEV_POWER_USAGE",
    "DCGM_FI_DEV_FB_USED",
    "DCGM_FI_DEV_FB_FREE",
]


def main() -> int:
    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "metrics_found": [],
        "metrics_missing": [],
    }

    # Find a DCGM exporter pod
    dcgm_pod = ""
    gpu_ns = ""
    for ns in GPU_NS_CANDIDATES:
        r = subprocess.run(["kubectl", "get", "pods", "-n", ns, "--no-headers"],
                           capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            for line in r.stdout.strip().split("\n"):
                if "dcgm" in line.lower() and "Running" in line:
                    dcgm_pod = line.split()[0]
                    gpu_ns = ns
                    break
        if dcgm_pod:
            break

    if not dcgm_pod:
        result["error"] = "No running DCGM exporter pod found"
        print(json.dumps(result, indent=2))
        return 1

    # Scrape metrics from the pod
    r = subprocess.run(
        ["kubectl", "exec", dcgm_pod, "-n", gpu_ns, "--",
         "curl", "-s", "http://localhost:9400/metrics"],
        capture_output=True, text=True, timeout=30,
    )
    if r.returncode != 0:
        # Fallback: port-forward and curl
        r = subprocess.run(
            ["kubectl", "exec", dcgm_pod, "-n", gpu_ns, "--",
             "wget", "-qO-", "http://localhost:9400/metrics"],
            capture_output=True, text=True, timeout=30,
        )

    metrics_text = r.stdout if r.returncode == 0 else ""

    for metric in EXPECTED_METRICS:
        if metric in metrics_text:
            result["metrics_found"].append(metric)
        else:
            result["metrics_missing"].append(metric)

    result["total_lines"] = len(metrics_text.strip().split("\n")) if metrics_text else 0
    result["success"] = len(result["metrics_found"]) > 0

    if result["metrics_missing"]:
        result["warning"] = f"Missing metrics: {', '.join(result['metrics_missing'])}"

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
