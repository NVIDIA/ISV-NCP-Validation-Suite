#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Topology-based placement test for bare-metal - TEMPLATE.

This script validates that the platform supports topology-aware placement
for bare-metal instances (e.g., placement groups, rack-awareness, spine-leaf
topology constraints).

Required JSON output:
{
    "success": true,
    "platform": "bm",
    "instance_id": "<id>",
    "placement_supported": true,
    "availability_zone": "us-west-2a",
    "placement_group": "<group-name>",
    "placement_strategy": "cluster",
    "operations": {
        "create_group":    {"passed": true},
        "verify_instance": {"passed": true},
        "describe_group":  {"passed": true},
        "delete_group":    {"passed": true}
    }
}

Usage:
    python topology_placement.py --instance-id <id> --region us-west-2

Reference implementation: ../aws/bare_metal/topology_placement.py
"""

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Topology-based placement test (template)")
    parser.add_argument("--instance-id", required=True, help="Instance ID")
    parser.add_argument("--region", default="us-west-2", help="Cloud region")
    args = parser.parse_args()

    result: dict = {
        "success": False,
        "platform": "bm",
        "instance_id": args.instance_id,
        "placement_supported": False,
        "availability_zone": "",
        "placement_group": "",
        "placement_strategy": "",
        "operations": {
            "create_group": {"passed": False},
            "verify_instance": {"passed": False},
            "describe_group": {"passed": False},
            "delete_group": {"passed": False},
        },
    }

    # TODO: Replace with your platform's topology placement implementation
    result["error"] = "Not implemented - replace with your platform's topology placement logic"
    print(json.dumps(result, indent=2))

    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
