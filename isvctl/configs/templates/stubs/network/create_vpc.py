#!/usr/bin/env python3
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
    "subnets": [                           # list    - created subnets
      {"subnet_id": "subnet-abc123"},
      {"subnet_id": "subnet-def456"}
    ],
    "security_group_id": "sg-abc123",      # string  - default security group ID
    "cidr_block": "10.0.0.0/16"            # string  - the CIDR block assigned
  }

On failure, set "success": false and include an "error" field:
  {
    "success": false,
    "platform": "network",
    "error": "descriptive error message"
  }

Usage:
    python create_vpc.py --name isv-shared-vpc --region us-west-2 --cidr 10.0.0.0/16

Reference implementation: ../../../stubs/aws/network/create_vpc.py
"""

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Create VPC / virtual network (template)")
    parser.add_argument("--name", default="isv-shared-vpc", help="Name tag for the VPC")
    parser.add_argument("--region", default="us-west-2", help="Cloud region")
    parser.add_argument("--cidr", default="10.0.0.0/16", help="CIDR block for the VPC")
    args = parser.parse_args()

    result: dict = {
        "success": False,
        "platform": "network",
        "network_id": "",
        "subnets": [],
        "security_group_id": "",
        "cidr_block": args.cidr,
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

    result["error"] = "Not implemented - replace with your platform's VPC creation logic"
    print(json.dumps(result, indent=2))

    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
