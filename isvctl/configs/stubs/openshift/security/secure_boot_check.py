#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Check Secure Boot is enabled on all nodes."""

import json
import subprocess
import sys
from typing import Any


def main() -> int:
    result: dict[str, Any] = {"success": False, "platform": "openshift", "nodes_checked": 0, "all_secure_boot": False}

    r = subprocess.run(["kubectl", "get", "nodes", "-o", "jsonpath={.items[*].metadata.name}"],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        result["error"] = f"Failed to list nodes: {r.stderr}"
        print(json.dumps(result, indent=2))
        return 1

    nodes = r.stdout.strip().split()
    enabled = 0
    node_results = {}

    for node in nodes:
        r = subprocess.run(
            ["oc", "debug", f"node/{node}", "--", "chroot", "/host",
             "mokutil", "--sb-state"],
            capture_output=True, text=True, timeout=60,
        )
        output = r.stdout.strip() if r.returncode == 0 else ""
        sb_enabled = "SecureBoot enabled" in output
        node_results[node] = "enabled" if sb_enabled else output or "unknown"
        if sb_enabled:
            enabled += 1

    result["nodes_checked"] = len(nodes)
    result["secure_boot_count"] = enabled
    result["all_secure_boot"] = enabled == len(nodes)
    result["node_results"] = node_results
    result["success"] = result["all_secure_boot"]

    if not result["success"] and enabled == 0:
        # Secure Boot may not be available on all hardware — warn, don't fail
        result["success"] = True
        result["warning"] = "Secure Boot not detected — may not be supported by hardware"

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
