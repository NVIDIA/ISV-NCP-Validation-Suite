#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Create a shared VPC with prefix and subnet in Carbide.

Sets up the base network resources used by subsequent test steps.

Usage:
    python create_vpc.py --site-id <site-id>

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
    parser = argparse.ArgumentParser(description="Create Carbide VPC + prefix + subnet")
    parser.add_argument("--region", default=os.environ.get("CARBIDE_REGION", "us-west-2"))
    parser.add_argument("--site-id", default=os.environ.get("CARBIDE_SITE_ID", ""))
    args = parser.parse_args()

    if not args.site_id:
        print(json.dumps({
            "success": False,
            "platform": "network",
            "error": "site-id is required (--site-id or CARBIDE_SITE_ID env var)",
        }, indent=2))
        return 1

    vpc_name = f"ncp-net-{int(time.time())}"
    cidr = "10.100.0.0/24"
    subnet_cidr = "10.100.0.0/26"

    result: dict[str, Any] = {
        "success": False,
        "platform": "network",
    }

    try:
        # Create VPC
        vpc_resp = run_carbide(
            "vpc", "create",
            "--name", vpc_name,
            "--description", "NCP network validation VPC",
            "--site-id", args.site_id,
        )
        vpc_id = vpc_resp.get("id", vpc_resp.get("vpc_id", ""))

        # Create VPC prefix
        prefix_resp = run_carbide(
            "vpc-prefix", "create",
            "--vpc-id", vpc_id,
            "--cidr", cidr,
        )
        prefix_id = prefix_resp.get("id", prefix_resp.get("prefix_id", ""))

        # Create subnet
        subnet_resp = run_carbide(
            "subnet", "create",
            "--vpc-id", vpc_id,
            "--cidr", subnet_cidr,
            "--name", f"{vpc_name}-subnet-0",
        )
        subnet_id = subnet_resp.get("id", subnet_resp.get("subnet_id", ""))

        result["network_id"] = vpc_id
        result["cidr"] = cidr
        result["subnets"] = [{"subnet_id": subnet_id, "cidr": subnet_cidr}]
        result["success"] = True

        # Persist for subsequent steps
        state = load_state()
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
