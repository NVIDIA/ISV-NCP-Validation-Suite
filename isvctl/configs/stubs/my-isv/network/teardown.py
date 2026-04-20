#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Teardown VPC / virtual network - TEMPLATE (replace with your platform implementation).

This script is called during the "teardown" phase. It must:
  1. Terminate all instances in the VPC (wait for termination)
  2. Delete key pairs created by test scripts (e.g., isv-dhcp-test-key)
  3. Delete all subnets in the VPC
  4. Delete all security groups (except platform default, if any)
  5. Detach and delete internet gateways
  6. Delete the VPC itself
  7. Print a JSON object to stdout

The script should be IDEMPOTENT - if a resource is already deleted, skip
it and continue with the rest.

Required JSON output fields:
  {
    "success": true,                                  # boolean - did teardown succeed?
    "platform": "network",                            # string  - always "network"
    "resources_deleted": [                            # list    - what was cleaned up
      "subnet:subnet-abc123",
      "security-group:sg-abc123",
      "internet-gateway:igw-abc123",
      "vpc:vpc-abc123"
    ],
    "message": "VPC and all resources deleted"        # string  - human-readable status
  }

On failure, set "success": false and include an "error" field.
If the VPC doesn't exist, return success (idempotent teardown).

Usage:
    python teardown.py --vpc-id vpc-abc123 --region <region>
    python teardown.py --vpc-id vpc-abc123 --region <region> --skip-destroy

Reference implementation: ../../aws/network/teardown.py
"""

import argparse
import json
import os
import sys

# ISVCTL_DEMO_MODE=1 enables demo-success output (used by `make demo-test`).
DEMO_MODE = os.environ.get("ISVCTL_DEMO_MODE") == "1"


def main() -> int:
    parser = argparse.ArgumentParser(description="Teardown VPC / virtual network (template)")
    parser.add_argument("--vpc-id", required=True, help="VPC / network ID to delete")
    parser.add_argument("--region", required=True, help="Cloud region")
    parser.add_argument("--skip-destroy", action="store_true", help="Skip actual deletion")
    args = parser.parse_args()

    result: dict = {
        "success": False,
        "platform": "network",
        "resources_deleted": [],
        "message": "",
    }

    if args.skip_destroy:
        result["success"] = True
        result["message"] = "Destroy skipped (--skip-destroy flag)"
        print(json.dumps(result, indent=2))
        return 0

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  TODO: Replace this block with your platform's VPC teardown      ║
    # ║                                                                  ║
    # ║  Example (pseudocode):                                           ║
    # ║    client = MyCloudClient(region=args.region)                    ║
    # ║                                                                  ║
    # ║    # Delete subnets                                              ║
    # ║    for subnet in client.list_subnets(vpc_id=args.vpc_id):        ║
    # ║        client.delete_subnet(subnet.id)                           ║
    # ║        result["resources_deleted"].append(f"subnet:{subnet.id}") ║
    # ║                                                                  ║
    # ║    # Delete security groups                                      ║
    # ║    for sg in client.list_security_groups(vpc_id=args.vpc_id):    ║
    # ║        if not sg.is_default:                                     ║
    # ║            client.delete_security_group(sg.id)                   ║
    # ║            result["resources_deleted"].append(f"sg:{sg.id}")     ║
    # ║                                                                  ║
    # ║    # Detach and delete internet gateways                         ║
    # ║    for igw in client.list_igws(vpc_id=args.vpc_id):              ║
    # ║        client.detach_igw(igw.id, args.vpc_id)                    ║
    # ║        client.delete_igw(igw.id)                                 ║
    # ║        result["resources_deleted"].append(f"igw:{igw.id}")       ║
    # ║                                                                  ║
    # ║    # Delete the VPC                                              ║
    # ║    client.delete_vpc(args.vpc_id)                                ║
    # ║    result["resources_deleted"].append(f"vpc:{args.vpc_id}")      ║
    # ║    result["success"] = True                                      ║
    # ║    result["message"] = "VPC and all resources deleted"           ║
    # ║                                                                  ║
    # ║  If VPC not found, still return success (idempotent):            ║
    # ║    result["success"] = True                                      ║
    # ║    result["message"] = "VPC not found (already deleted)"         ║
    # ╚══════════════════════════════════════════════════════════════════╝

    if DEMO_MODE:
        result["resources_deleted"].append(f"vpc:{args.vpc_id}")
        result["resources_deleted"].append("security-group:dummy-sg-shared")
        result["resources_deleted"].append("subnet:dummy-subnet-a")
        result["resources_deleted"].append("subnet:dummy-subnet-b")
        result["message"] = "Shared VPC and associated resources deleted"
        result["success"] = True
    else:
        result["error"] = "Not implemented - replace with your platform's VPC teardown logic"

    print(json.dumps(result, indent=2))

    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
