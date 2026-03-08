#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Check hugepage configuration on nodes."""

import json
import subprocess
import sys
from typing import Any


def main() -> int:
    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "hugepages_available": False,
    }

    # Check hugepage capacity from node status
    r = subprocess.run(
        ["kubectl", "get", "nodes", "-o",
         "jsonpath={range .items[*]}{.metadata.name}{'\\t'}{.status.capacity.hugepages-1Gi}{'\\t'}{.status.capacity.hugepages-2Mi}{'\\n'}{end}"],
        capture_output=True, text=True, timeout=30,
    )
    if r.returncode != 0:
        result["error"] = f"Failed to query nodes: {r.stderr}"
        print(json.dumps(result, indent=2))
        return 1

    node_hugepages = {}
    for line in r.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            name = parts[0]
            hp_1g = parts[1] if parts[1] else "0"
            hp_2m = parts[2] if parts[2] else "0"
            node_hugepages[name] = {"1Gi": hp_1g, "2Mi": hp_2m}

    result["node_hugepages"] = node_hugepages
    result["nodes_checked"] = len(node_hugepages)

    # Check if any node has hugepages
    has_1g = any(v.get("1Gi", "0") not in ("0", "") for v in node_hugepages.values())
    has_2m = any(v.get("2Mi", "0") not in ("0", "") for v in node_hugepages.values())

    result["hugepages_1gi_available"] = has_1g
    result["hugepages_2mi_available"] = has_2m
    result["hugepages_available"] = has_1g or has_2m
    result["success"] = True  # Report status, don't fail if no hugepages

    if not result["hugepages_available"]:
        result["info"] = "No hugepages configured — may be needed for VFIO passthrough"

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
