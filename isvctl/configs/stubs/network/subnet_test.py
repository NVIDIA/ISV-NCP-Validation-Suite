#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Subnet configuration test - TEMPLATE (replace with your platform implementation).

This script is called during the "test" phase. It is SELF-CONTAINED:
  1. Create a temporary VPC
  2. Create N subnets distributed across availability zones
  3. Verify route tables are associated with each subnet
  4. Clean up all resources
  5. Print a JSON object to stdout

Required JSON output fields:
  {
    "success": true,                        # boolean - did all checks pass?
    "platform": "network",                  # string  - always "network"
    "test_name": "subnet_config",           # string  - always "subnet_config"
    "network_id": "vpc-abc123",             # string  - VPC used for the test
    "subnets": [                            # list    - created subnets
      {
        "subnet_id": "subnet-abc123",       # string  - subnet identifier
        "cidr": "10.98.0.0/24",             # string  - subnet CIDR
        "availability_zone": "<az>"         # string  - AZ placement
      }
    ],
    "route_tables_verified": true           # boolean - route tables OK?
  }

On failure, set "success": false and include an "error" field.

Usage:
    python subnet_test.py --region <region> --cidr 10.98.0.0/16 --subnet-count 4

Reference implementation: ../aws/network/subnet_test.py
"""

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Subnet configuration test (template)")
    parser.add_argument("--region", required=True, help="Cloud region")
    parser.add_argument("--cidr", default="10.98.0.0/16", help="CIDR block for test VPC")
    parser.add_argument("--subnet-count", type=int, default=4, help="Number of subnets to create")
    args = parser.parse_args()  # noqa: F841 — used in TODO block below

    result: dict = {
        "success": False,
        "platform": "network",
        "test_name": "subnet_config",
        "network_id": "",
        "subnets": [],
        "route_tables_verified": False,
    }

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  TODO: Replace this block with your platform's subnet test       ║
    # ║                                                                  ║
    # ║  Example (pseudocode):                                           ║
    # ║    client = MyCloudClient(region=args.region)                    ║
    # ║    vpc = client.create_vpc(cidr=args.cidr)                       ║
    # ║    result["network_id"] = vpc.id                                 ║
    # ║                                                                  ║
    # ║    azs = client.availability_zones()                             ║
    # ║    for i in range(args.subnet_count):                            ║
    # ║        az = azs[i % len(azs)]                                    ║
    # ║        subnet = client.create_subnet(vpc.id, az, sub_cidr)       ║
    # ║        result["subnets"].append({                                ║
    # ║            "subnet_id": subnet.id,                               ║
    # ║            "cidr": sub_cidr,                                     ║
    # ║            "availability_zone": az,                              ║
    # ║        })                                                        ║
    # ║                                                                  ║
    # ║    # Verify route tables                                         ║
    # ║    for s in result["subnets"]:                                   ║
    # ║        assert client.get_route_table(s["subnet_id"])             ║
    # ║    result["route_tables_verified"] = True                        ║
    # ║                                                                  ║
    # ║    # Cleanup                                                     ║
    # ║    client.delete_vpc(vpc.id, cascade=True)                       ║
    # ║    result["success"] = True                                      ║
    # ╚══════════════════════════════════════════════════════════════════╝

    result["error"] = "Not implemented - replace with your platform's subnet test logic"
    print(json.dumps(result, indent=2))

    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
