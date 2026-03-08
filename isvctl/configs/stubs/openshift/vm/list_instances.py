#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""List VirtualMachineInstances in the test namespace."""

import json
import os
import subprocess
import sys
from typing import Any

NAMESPACE = os.environ.get("VM_NAMESPACE", "ncp-vm-validation")
TARGET = "ncp-gpu-vm"


def main() -> int:
    result: dict[str, Any] = {
        "success": False,
        "platform": "vm",
        "instances": [],
        "count": 0,
        "found_target": False,
        "target_instance": TARGET,
    }

    r = subprocess.run(
        ["kubectl", "get", "vmi", "-n", NAMESPACE, "-o", "json"],
        capture_output=True, text=True, timeout=30,
    )
    if r.returncode != 0:
        result["error"] = f"Failed to list VMIs: {r.stderr}"
        print(json.dumps(result, indent=2))
        return 1

    data = json.loads(r.stdout)
    for item in data.get("items", []):
        name = item["metadata"]["name"]
        phase = item.get("status", {}).get("phase", "Unknown")
        ips = item.get("status", {}).get("interfaces", [])
        ip = ips[0].get("ipAddress", "") if ips else ""
        result["instances"].append({
            "instance_id": name,
            "state": phase.lower(),
            "public_ip": ip,
            "private_ip": ip,
        })
        if name == TARGET:
            result["found_target"] = True

    result["count"] = len(result["instances"])
    result["success"] = True

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
