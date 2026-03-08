#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Check DCGM Exporter is running and exposing metrics."""

import json
import subprocess
import sys
from typing import Any

GPU_NS_CANDIDATES = ["nvidia-gpu-operator", "gpu-operator", "openshift-operators"]


def main() -> int:
    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "exporter_running": False,
        "metrics_endpoint": "",
        "pod_count": 0,
    }

    # Find GPU operator namespace
    gpu_ns = ""
    for ns in GPU_NS_CANDIDATES:
        r = subprocess.run(["kubectl", "get", "pods", "-n", ns, "-l",
                            "app=nvidia-dcgm-exporter", "--no-headers"],
                           capture_output=True, text=True, timeout=30)
        if r.returncode == 0 and r.stdout.strip():
            gpu_ns = ns
            break

    if not gpu_ns:
        # Try broader label
        for ns in GPU_NS_CANDIDATES:
            r = subprocess.run(["kubectl", "get", "pods", "-n", ns, "--no-headers"],
                               capture_output=True, text=True, timeout=30)
            if r.returncode == 0 and "dcgm" in r.stdout.lower():
                gpu_ns = ns
                break

    if not gpu_ns:
        result["error"] = "DCGM Exporter pods not found in any known namespace"
        print(json.dumps(result, indent=2))
        return 1

    result["namespace"] = gpu_ns

    # Count running DCGM exporter pods
    r = subprocess.run(["kubectl", "get", "pods", "-n", gpu_ns, "--no-headers"],
                       capture_output=True, text=True, timeout=30)
    dcgm_pods = [l for l in r.stdout.strip().split("\n")
                 if "dcgm" in l.lower() and "Running" in l]
    result["pod_count"] = len(dcgm_pods)
    result["exporter_running"] = len(dcgm_pods) > 0

    # Check metrics service
    r = subprocess.run(["kubectl", "get", "svc", "-n", gpu_ns, "-l",
                        "app=nvidia-dcgm-exporter",
                        "-o", "jsonpath={.items[0].metadata.name}"],
                       capture_output=True, text=True, timeout=30)
    svc_name = r.stdout.strip() if r.returncode == 0 else ""
    if svc_name:
        result["metrics_endpoint"] = f"{svc_name}.{gpu_ns}.svc:9400/metrics"

    # Check ServiceMonitor exists (for Prometheus scraping)
    r = subprocess.run(["kubectl", "get", "servicemonitor", "-n", gpu_ns,
                        "--no-headers"],
                       capture_output=True, text=True, timeout=30)
    result["service_monitor_exists"] = r.returncode == 0 and "dcgm" in r.stdout.lower()

    result["success"] = result["exporter_running"]

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
