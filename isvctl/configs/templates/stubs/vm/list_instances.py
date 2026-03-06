#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""List VM instances in a network/VPC.

Template stub for ISV NCP Validation. Replace the TODO section with your
platform's API calls to enumerate instances and optionally filter by ID.

This script must:
  1. Query your platform for instances in the given VPC/network
  2. Return each instance's ID and current state
  3. Optionally filter to a specific instance ID

Required JSON output fields:
  success      (bool)  - whether the operation succeeded
  platform     (str)   - always "vm"
  instances    (list)  - list of {"instance_id": str, "state": str}
  total_count  (int)   - number of instances returned
  error        (str, optional) - error message provided when success is false

Usage:
    python list_instances.py --vpc-id vpc-xxx --region us-west-2
    python list_instances.py --vpc-id vpc-xxx --instance-id i-xxx --region us-west-2

Reference implementation (AWS):
    ../../../stubs/aws/vm/list_instances.py
"""

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="List VM instances in a VPC/network")
    parser.add_argument("--vpc-id", required=True, help="VPC or network identifier")
    parser.add_argument("--instance-id", help="Filter to a specific instance ID")
    parser.add_argument("--region", default="us-west-2", help="Cloud region")
    args = parser.parse_args()  # noqa: F841 — used in TODO block below

    result = {
        "success": False,
        "platform": "vm",
        "instances": [],
        "total_count": 0,
    }

    try:
        # ╔══════════════════════════════════════════════════════════════╗
        # ║  TODO: Replace this block with your platform's API calls     ║
        # ║                                                              ║
        # ║  1. List all instances in the VPC/network                    ║
        # ║     instances = list_instances(                              ║
        # ║         vpc_id=args.vpc_id,                                  ║
        # ║         region=args.region,                                  ║
        # ║     )                                                        ║
        # ║                                                              ║
        # ║  2. If --instance-id is provided, filter the list            ║
        # ║     if args.instance_id:                                     ║
        # ║         instances = [i for i in instances                    ║
        # ║                      if i["id"] == args.instance_id]         ║
        # ║                                                              ║
        # ║  3. Build the instances list                                 ║
        # ║     for inst in instances:                                   ║
        # ║         result["instances"].append({                         ║
        # ║             "instance_id": inst["id"],                       ║
        # ║             "state": inst["state"],                          ║
        # ║         })                                                   ║
        # ║                                                              ║
        # ║  4. Set total_count and success                              ║
        # ║     result["total_count"] = len(result["instances"])         ║
        # ║     result["success"] = True                                 ║
        # ╚══════════════════════════════════════════════════════════════╝

        result["error"] = "Not implemented - replace with your platform's instance listing logic"

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
