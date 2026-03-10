#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Check SELinux is in Enforcing mode on all nodes."""

import json
import subprocess
import sys
from typing import Any


def main() -> int:
    result: dict[str, Any] = {"success": False, "platform": "openshift", "nodes_checked": 0, "all_enforcing": False}

    r = subprocess.run(["kubectl", "get", "nodes", "-o", "jsonpath={.items[*].metadata.name}"],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        result["error"] = f"Failed to list nodes: {r.stderr}"
        print(json.dumps(result, indent=2))
        return 1

    nodes = r.stdout.strip().split()
    enforcing = 0
    node_results = {}

    for node in nodes:
        r = subprocess.run(
            ["oc", "debug", f"node/{node}", "--", "chroot", "/host", "getenforce"],
            capture_output=True, text=True, timeout=60,
        )
        status = r.stdout.strip() if r.returncode == 0 else "Unknown"
        node_results[node] = status
        if status == "Enforcing":
            enforcing += 1

    result["nodes_checked"] = len(nodes)
    result["enforcing_count"] = enforcing
    result["all_enforcing"] = enforcing == len(nodes)
    result["node_results"] = node_results
    result["success"] = result["all_enforcing"]

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
