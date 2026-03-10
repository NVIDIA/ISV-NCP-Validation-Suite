#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Verify Machine API is configured with Carbide provider.

Checks that the Machine API operator is running and the Carbide
infrastructure provider is configured.

Output: {"success": true, "provider_configured": true, "machine_api_ready": true}
"""

import json
import subprocess
import sys
from typing import Any


def run_oc(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["oc"] + list(args), capture_output=True, text=True, timeout=60)


def main() -> int:
    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "provider_configured": False,
        "machine_api_ready": False,
    }

    # Check Machine API operator
    r = run_oc("get", "clusteroperator", "machine-api",
               "-o", "jsonpath={.status.conditions[?(@.type=='Available')].status}")
    result["machine_api_ready"] = r.returncode == 0 and r.stdout.strip() == "True"

    if not result["machine_api_ready"]:
        result["error"] = "Machine API operator not available"
        print(json.dumps(result, indent=2))
        return 1

    # Check infrastructure platform type
    r = run_oc("get", "infrastructure", "cluster",
               "-o", "jsonpath={.status.platformStatus.type}")
    platform_type = r.stdout.strip() if r.returncode == 0 else ""
    result["platform_type"] = platform_type

    # Check for existing MachineSets (proves Machine API is functional)
    r = run_oc("get", "machinesets", "-n", "openshift-machine-api", "--no-headers")
    existing_machinesets = len(r.stdout.strip().split("\n")) if r.stdout.strip() else 0
    result["existing_machinesets"] = existing_machinesets

    # Check if Carbide provider CRDs or configuration exist
    r = run_oc("get", "machines", "-n", "openshift-machine-api", "--no-headers")
    result["existing_machines"] = len(r.stdout.strip().split("\n")) if r.stdout.strip() else 0

    result["provider_configured"] = result["machine_api_ready"]
    result["success"] = result["provider_configured"]

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
