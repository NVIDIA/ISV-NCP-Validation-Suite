#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Check Node Health Check (NHC) operator status."""

import json
import subprocess
import sys
from typing import Any


def main() -> int:
    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "nhc_installed": False,
        "nhc_configs": 0,
    }

    # Check for NodeHealthCheck CRD
    r = subprocess.run(
        ["kubectl", "get", "crd", "nodehealthchecks.remediation.medik8s.io",
         "--no-headers"],
        capture_output=True, text=True, timeout=30,
    )
    if r.returncode != 0:
        result["success"] = True
        result["info"] = "NHC operator not installed — skipping"
        print(json.dumps(result, indent=2))
        return 0

    result["nhc_installed"] = True

    # Check NodeHealthCheck resources
    r = subprocess.run(
        ["kubectl", "get", "nodehealthcheck", "--all-namespaces", "-o", "json"],
        capture_output=True, text=True, timeout=30,
    )
    if r.returncode == 0:
        data = json.loads(r.stdout)
        result["nhc_configs"] = len(data.get("items", []))
        for item in data.get("items", []):
            name = item["metadata"]["name"]
            phase = item.get("status", {}).get("phase", "Unknown")
            result.setdefault("configs", []).append({"name": name, "phase": phase})

    # Check for MachineHealthCheck (OpenShift native alternative)
    r = subprocess.run(
        ["kubectl", "get", "machinehealthcheck", "-n", "openshift-machine-api",
         "--no-headers"],
        capture_output=True, text=True, timeout=30,
    )
    if r.returncode == 0 and r.stdout.strip():
        mhc_count = len(r.stdout.strip().split("\n"))
        result["machine_health_checks"] = mhc_count

    result["success"] = True

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
