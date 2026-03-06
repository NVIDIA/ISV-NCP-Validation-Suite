#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Test subnet creation in the shared Carbide VPC.

Creates multiple subnets in the VPC from the setup step and verifies
they are available.

Usage:
    python subnet_test.py --site-id <site-id>

Output JSON:
{
    "success": true,
    "platform": "network",
    "subnets": [...],
    "tests": {
        "create_subnets": {"passed": true},
        "subnets_available": {"passed": true}
    }
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


# Subnet CIDRs within the 10.100.0.0/24 prefix
SUBNET_CIDRS = [
    "10.100.0.64/26",
    "10.100.0.128/26",
    "10.100.0.192/26",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Carbide subnet test")
    parser.add_argument("--region", default=os.environ.get("CARBIDE_REGION", "us-west-2"))
    parser.add_argument("--site-id", default=os.environ.get("CARBIDE_SITE_ID", ""))
    args = parser.parse_args()

    state = load_state()
    vpc_id = state.get("network_vpc_id", "")

    result: dict[str, Any] = {
        "success": False,
        "platform": "network",
        "subnets": [],
        "tests": {},
    }

    if not vpc_id:
        result["error"] = "no network_vpc_id in state; run create_vpc first"
        print(json.dumps(result, indent=2))
        return 1

    created_ids: list[str] = []

    try:
        # CREATE subnets
        ts = int(time.time())
        for i, cidr in enumerate(SUBNET_CIDRS):
            resp = run_carbide(
                "subnet", "create",
                "--vpc-id", vpc_id,
                "--cidr", cidr,
                "--name", f"ncp-subnet-{ts}-{i}",
            )
            sid = resp.get("id", resp.get("subnet_id", ""))
            created_ids.append(sid)
            result["subnets"].append({"subnet_id": sid, "cidr": cidr})

        result["tests"]["create_subnets"] = {"passed": len(created_ids) == len(SUBNET_CIDRS)}

        # VERIFY subnets via list
        list_resp = run_carbide("subnet", "list", "--vpc-id", vpc_id)
        listed = list_resp if isinstance(list_resp, list) else list_resp.get("subnets", [])
        listed_ids = {s.get("id", s.get("subnet_id", "")) for s in listed}
        all_found = all(sid in listed_ids for sid in created_ids)
        result["tests"]["subnets_available"] = {"passed": all_found}

        all_passed = all(t.get("passed", False) for t in result["tests"].values())
        result["success"] = all_passed

        # Persist created subnet IDs for teardown
        existing = state.get("network_subnet_ids", [])
        state["network_subnet_ids"] = existing + created_ids
        save_state(state)

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
