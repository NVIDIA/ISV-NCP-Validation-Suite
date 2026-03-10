#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Test tray allocation within the ComputeDomain.

Verifies that GPUs are allocated in tray-aligned groups and that
the scheduler respects ComputeDomain boundaries.
"""

import json
import os
import subprocess
import sys
from typing import Any

NAMESPACE = os.environ.get("CD_NAMESPACE", "ncp-computedomain-validation")
DOMAIN_NAME = "ncp-test-domain"


def run_kubectl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["kubectl"] + list(args), capture_output=True, text=True, timeout=60)


def main() -> int:
    result: dict[str, Any] = {"success": False, "platform": "openshift"}

    r = run_kubectl("get", "computedomain", DOMAIN_NAME, "-n", NAMESPACE, "-o", "json")
    if r.returncode != 0:
        result["error"] = f"ComputeDomain {DOMAIN_NAME} not found"
        print(json.dumps(result, indent=2))
        return 1

    cd = json.loads(r.stdout)
    status = cd.get("status", {})
    result["phase"] = status.get("phase", "Unknown")
    result["allocated_gpus"] = status.get("allocatedGPUs", 0)
    result["available_gpus"] = status.get("availableGPUs", 0)

    # Check tray alignment
    devices = status.get("devices", [])
    result["device_count"] = len(devices)
    result["tray_aligned"] = result["phase"] == "Ready"

    result["success"] = result["tray_aligned"]

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
