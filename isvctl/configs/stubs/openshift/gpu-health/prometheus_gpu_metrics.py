#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Verify Prometheus is scraping GPU metrics.

Queries the OpenShift Thanos/Prometheus endpoint for GPU metrics
to confirm the monitoring pipeline works end-to-end.
"""

import json
import subprocess
import sys
from typing import Any

METRIC_QUERIES = [
    "DCGM_FI_DEV_GPU_UTIL",
    "DCGM_FI_DEV_GPU_TEMP",
    "DCGM_FI_DEV_POWER_USAGE",
]


def main() -> int:
    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "metrics_in_prometheus": [],
        "metrics_missing": [],
    }

    # Get Thanos querier route
    r = subprocess.run(
        ["oc", "get", "route", "thanos-querier", "-n", "openshift-monitoring",
         "-o", "jsonpath={.spec.host}"],
        capture_output=True, text=True, timeout=30,
    )
    if r.returncode != 0 or not r.stdout.strip():
        result["error"] = "Thanos querier route not found"
        print(json.dumps(result, indent=2))
        return 1

    thanos_host = r.stdout.strip()

    # Get bearer token for Prometheus access
    r = subprocess.run(["oc", "whoami", "-t"], capture_output=True, text=True, timeout=10)
    token = r.stdout.strip() if r.returncode == 0 else ""

    if not token:
        result["error"] = "Could not get bearer token for Prometheus"
        print(json.dumps(result, indent=2))
        return 1

    # Query each metric
    for metric in METRIC_QUERIES:
        r = subprocess.run(
            ["curl", "-sk",
             f"https://{thanos_host}/api/v1/query?query={metric}",
             "-H", f"Authorization: Bearer {token}"],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode == 0:
            try:
                data = json.loads(r.stdout)
                if data.get("status") == "success":
                    results = data.get("data", {}).get("result", [])
                    if results:
                        result["metrics_in_prometheus"].append(metric)
                        continue
            except json.JSONDecodeError:
                pass
        result["metrics_missing"].append(metric)

    result["success"] = len(result["metrics_in_prometheus"]) > 0

    if result["metrics_missing"]:
        result["warning"] = f"Metrics not in Prometheus: {', '.join(result['metrics_missing'])}"

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
