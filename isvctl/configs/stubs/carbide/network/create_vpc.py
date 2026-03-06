#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Create or reuse a VPC with prefix and subnet in Carbide.

Sets up the base network resources used by subsequent test steps.
Supports pre-existing resources via environment variables.

Usage:
    python create_vpc.py --site-id <site-id>
    CARBIDE_VPC_ID=<uuid> CARBIDE_VPC_PREFIX_ID=<uuid> CARBIDE_SUBNET_ID=<uuid> python create_vpc.py

Output JSON:
{
    "success": true,
    "platform": "network",
    "network_id": "<vpc-id>",
    "cidr": "10.100.0.0/24",
    "subnets": [{"subnet_id": "...", "cidr": "..."}]
}
"""

import argparse
import json
import os
import sys
import time
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common.carbide import load_state, run_carbide, save_state


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or reuse Carbide VPC + prefix + subnet")
    parser.add_argument("--region", default=os.environ.get("CARBIDE_REGION", "us-west-2"))
    parser.add_argument("--site-id", default=os.environ.get("CARBIDE_SITE_ID", ""))
    parser.add_argument("--vpc-id", default=os.environ.get("CARBIDE_VPC_ID", ""))
    parser.add_argument("--vpc-prefix-id", default=os.environ.get("CARBIDE_VPC_PREFIX_ID", ""))
    parser.add_argument("--subnet-id", default=os.environ.get("CARBIDE_SUBNET_ID", ""))
    args = parser.parse_args()

    cidr = "10.100.0.0/24"
    subnet_cidr = "10.100.0.0/26"

    result: dict[str, Any] = {
        "success": False,
        "platform": "network",
    }

    try:
        state = load_state()

        # VPC: reuse or create
        if args.vpc_id:
            vpc_resp = run_carbide("vpc", "get", args.vpc_id)
            vpc_id = vpc_resp.get("id", args.vpc_id)
            vpc_name = vpc_resp.get("name", args.vpc_id)
            state["network_vpc_created"] = False
        else:
            if not args.site_id:
                result["error"] = "site-id required when not using pre-existing VPC"
                print(json.dumps(result, indent=2))
                return 1
            vpc_name = f"ncp-net-{int(time.time())}"
            vpc_resp = run_carbide(
                "vpc", "create",
                "--name", vpc_name,
                "--description", "NCP network validation VPC",
                "--site-id", args.site_id,
            )
            vpc_id = vpc_resp.get("id", vpc_resp.get("vpc_id", ""))
            state["network_vpc_created"] = True

        # VPC Prefix: reuse or create
        if args.vpc_prefix_id:
            prefix_id = args.vpc_prefix_id
            state["network_prefix_created"] = False
        else:
            prefix_resp = run_carbide(
                "vpc-prefix", "create",
                "--vpc-id", vpc_id,
                "--cidr", cidr,
            )
            prefix_id = prefix_resp.get("id", prefix_resp.get("prefix_id", ""))
            state["network_prefix_created"] = True

        # Subnet: reuse or create
        if args.subnet_id:
            subnet_id = args.subnet_id
            state["network_subnet_created"] = False
        else:
            subnet_resp = run_carbide(
                "subnet", "create",
                "--vpc-id", vpc_id,
                "--cidr", subnet_cidr,
                "--name", f"{vpc_name}-subnet-0",
            )
            subnet_id = subnet_resp.get("id", subnet_resp.get("subnet_id", ""))
            state["network_subnet_created"] = True

        result["network_id"] = vpc_id
        result["cidr"] = cidr
        result["subnets"] = [{"subnet_id": subnet_id, "cidr": subnet_cidr}]
        result["success"] = True

        state["network_vpc_id"] = vpc_id
        state["network_vpc_name"] = vpc_name
        state["network_prefix_id"] = prefix_id
        state["network_subnet_ids"] = [subnet_id]
        state["site_id"] = args.site_id
        save_state(state)

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
