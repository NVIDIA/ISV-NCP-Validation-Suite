#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Create VPC / virtual network - TEMPLATE (replace with your platform implementation).

This script is called during the "setup" phase. It must:
  1. Create a VPC or virtual network with the given CIDR block
  2. Create subnets across availability zones
  3. Create a default security group
  4. Print a JSON object to stdout

Required JSON output fields:
  {
    "success": true,                       # boolean - did the operation succeed?
    "platform": "network",                 # string  - always "network"
    "network_id": "vpc-abc123",            # string  - VPC / network identifier
    "cidr": "10.0.0.0/16",                 # string  - the CIDR block assigned
    "subnets": [                           # list    - created subnets
      {"subnet_id": "subnet-abc123", "cidr": "10.0.1.0/24", "az": "<az>",
       "auto_assign_public_ip": true, "available_ips": 251}
    ],
    "security_group_id": "sg-abc123",      # string  - default security group ID
    "dhcp_options": {                      # object  - DHCP options configuration
      "dhcp_options_id": "dopt-abc",       # string  - DHCP options set ID
      "domain_name": "internal.example",   # string  - domain name
      "domain_name_servers": ["..."],      # list    - DNS servers
      "ntp_servers": []                    # list    - NTP servers (may be empty)
    }
  }

On failure, set "success": false and include an "error" field:
  {
    "success": false,
    "platform": "network",
    "error": "descriptive error message"
  }

Usage:
    python create_vpc.py --name isv-shared-vpc --region <region> --cidr 10.0.0.0/16

Reference implementation: ../../aws/network/create_vpc.py
"""

import argparse
import json
import os
import sys

# ISVCTL_DEMO_MODE=1 enables demo-success output (used by `make demo-test`).
DEMO_MODE = os.environ.get("ISVCTL_DEMO_MODE") == "1"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create VPC / virtual network (template)")
    parser.add_argument("--name", default="isv-shared-vpc", help="Name tag for the VPC")
    parser.add_argument("--region", required=True, help="Cloud region")
    parser.add_argument("--cidr", default="10.0.0.0/16", help="CIDR block for the VPC")
    args = parser.parse_args()

    result: dict = {
        "success": False,
        "platform": "network",
        "network_id": "",
        "cidr": args.cidr,
        "subnets": [],
        "security_group_id": "",
        "dhcp_options": None,
    }

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  TODO: Replace this block with your platform's VPC creation      ║
    # ║                                                                  ║
    # ║  Example (pseudocode):                                           ║
    # ║    client = MyCloudClient(region=args.region)                    ║
    # ║    vpc = client.create_vpc(name=args.name, cidr=args.cidr)       ║
    # ║    result["network_id"] = vpc.id                                 ║
    # ║                                                                  ║
    # ║    for i, az in enumerate(client.availability_zones()):          ║
    # ║        subnet = client.create_subnet(vpc.id, az, sub_cidr)       ║
    # ║        result["subnets"].append({"subnet_id": subnet.id})        ║
    # ║                                                                  ║
    # ║    sg = client.create_security_group(vpc.id, f"{args.name}-sg")  ║
    # ║    result["security_group_id"] = sg.id                           ║
    # ║    result["success"] = True                                      ║
    # ╚══════════════════════════════════════════════════════════════════╝

    if DEMO_MODE:
        result["network_id"] = "dummy-vpc-shared"
        result["subnets"] = [
            {
                "subnet_id": "dummy-subnet-a",
                "cidr": "10.0.1.0/24",
                "az": f"{args.region}a",
                "auto_assign_public_ip": True,
                "available_ips": 251,
            },
            {
                "subnet_id": "dummy-subnet-b",
                "cidr": "10.0.2.0/24",
                "az": f"{args.region}b",
                "auto_assign_public_ip": False,
                "available_ips": 251,
            },
        ]
        result["security_group_id"] = "dummy-sg-shared"
        result["dhcp_options"] = {
            "dhcp_options_id": "dummy-dopt",
            "domain_name": "internal.my-isv.test",
            "domain_name_servers": ["10.0.0.2"],
            "ntp_servers": [],
        }
        result["success"] = True
    else:
        result["error"] = "Not implemented - replace with your platform's VPC creation logic"

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
