#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""VPC CRUD lifecycle test - TEMPLATE (replace with your platform implementation).

This script is called during the "test" phase. It is SELF-CONTAINED:
  1. Create a temporary VPC
  2. Read its attributes
  3. Update tags / settings (e.g., DNS support)
  4. Delete the VPC
  5. Print a JSON object to stdout

Required JSON output fields (read by VpcCrudCheck -- must use these exact keys):
  {
    "success": true,                       # boolean - did all CRUD steps pass?
    "platform": "network",                 # string  - always "network"
    "test_name": "vpc_crud",               # string  - always "vpc_crud"
    "tests": {                             # object  - per-step results
      "create_vpc": {"passed": true, "vpc_id": "vpc-abc123"},
      "read_vpc":   {"passed": true, "attributes": {"cidr": "..."}},
      "update_tags":{"passed": true},
      "update_dns": {"passed": true},
      "delete_vpc": {"passed": true}
    }
  }

On failure, set "success": false and include an "error" field.

Usage:
    python vpc_crud_test.py --region <region> --cidr 10.99.0.0/16

Reference implementation: ../../aws/network/vpc_crud_test.py
"""

import argparse
import json
import os
import sys
from typing import Any

# ISVCTL_DEMO_MODE=1 enables demo-success output (used by `make demo-test`).
DEMO_MODE = os.environ.get("ISVCTL_DEMO_MODE") == "1"


def main() -> int:
    parser = argparse.ArgumentParser(description="VPC CRUD lifecycle test (template)")
    parser.add_argument("--region", required=True, help="Cloud region")
    parser.add_argument("--cidr", default="10.99.0.0/16", help="CIDR block for test VPC")
    args = parser.parse_args()

    result: dict[str, Any] = {
        "success": False,
        "platform": "network",
        "test_name": "vpc_crud",
        "tests": {
            "create_vpc": {"passed": False},
            "read_vpc": {"passed": False},
            "update_tags": {"passed": False},
            "update_dns": {"passed": False},
            "delete_vpc": {"passed": False},
        },
    }

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  TODO: Replace this block with your platform's VPC CRUD test     ║
    # ║                                                                  ║
    # ║  Example (pseudocode):                                           ║
    # ║    client = MyCloudClient(region=args.region)                    ║
    # ║                                                                  ║
    # ║    # CREATE                                                      ║
    # ║    vpc = client.create_vpc(cidr=args.cidr)                       ║
    # ║    result["tests"]["create_vpc"] = {"passed": True,              ║
    # ║                                     "vpc_id": vpc.id}            ║
    # ║                                                                  ║
    # ║    # READ                                                        ║
    # ║    attrs = client.describe_vpc(vpc.id)                           ║
    # ║    result["tests"]["read_vpc"] = {"passed": True,                ║
    # ║                                   "attributes": attrs}           ║
    # ║                                                                  ║
    # ║    # UPDATE                                                      ║
    # ║    client.tag_vpc(vpc.id, {"Environment": "test"})               ║
    # ║    result["tests"]["update_tags"] = {"passed": True}             ║
    # ║    client.enable_dns_support(vpc.id)                             ║
    # ║    result["tests"]["update_dns"] = {"passed": True}              ║
    # ║                                                                  ║
    # ║    # DELETE                                                      ║
    # ║    client.delete_vpc(vpc.id)                                     ║
    # ║    result["tests"]["delete_vpc"] = {"passed": True}              ║
    # ║    result["success"] = True                                      ║
    # ╚══════════════════════════════════════════════════════════════════╝

    if DEMO_MODE:
        result["tests"] = {
            "create_vpc": {"passed": True, "vpc_id": "dummy-vpc-crud"},
            "read_vpc": {"passed": True, "attributes": {"cidr": args.cidr}},
            "update_tags": {"passed": True},
            "update_dns": {"passed": True, "dns_support": True},
            "delete_vpc": {"passed": True},
        }
        result["success"] = True
    else:
        result["error"] = "Not implemented - replace with your platform's VPC CRUD logic"

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
