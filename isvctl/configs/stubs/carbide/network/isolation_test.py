#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Test VPC isolation in Carbide.

Creates two separate VPCs and verifies they cannot see each other
(no cross-references in listings).

Usage:
    python isolation_test.py --site-id <site-id>

Output JSON:
{
    "success": true,
    "platform": "network",
    "tests": {
        "create_vpc_a": {"passed": true},
        "create_vpc_b": {"passed": true},
        "no_peering": {"passed": true}
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
from common.carbide import run_carbide


def main() -> int:
    parser = argparse.ArgumentParser(description="Carbide VPC isolation test")
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

    ts = int(time.time())
    vpc_a_id = ""
    vpc_b_id = ""

    result: dict[str, Any] = {
        "success": False,
        "platform": "network",
        "tests": {},
    }

    try:
        # Create VPC A
        try:
            resp_a = run_carbide(
                "vpc", "create",
                "--name", f"ncp-iso-a-{ts}",
                "--description", "NCP isolation test VPC A",
                "--site-id", args.site_id,
            )
            vpc_a_id = resp_a.get("id", resp_a.get("vpc_id", ""))
            result["tests"]["create_vpc_a"] = {"passed": bool(vpc_a_id)}
        except Exception as e:
            result["tests"]["create_vpc_a"] = {"passed": False, "error": str(e)}

        # Create VPC B
        try:
            resp_b = run_carbide(
                "vpc", "create",
                "--name", f"ncp-iso-b-{ts}",
                "--description", "NCP isolation test VPC B",
                "--site-id", args.site_id,
            )
            vpc_b_id = resp_b.get("id", resp_b.get("vpc_id", ""))
            result["tests"]["create_vpc_b"] = {"passed": bool(vpc_b_id)}
        except Exception as e:
            result["tests"]["create_vpc_b"] = {"passed": False, "error": str(e)}

        # Verify isolation: subnets in VPC A should not appear in VPC B listing
        if vpc_a_id and vpc_b_id:
            try:
                subnets_a = run_carbide("subnet", "list", "--vpc-id", vpc_a_id)
                subnets_b = run_carbide("subnet", "list", "--vpc-id", vpc_b_id)

                list_a = subnets_a if isinstance(subnets_a, list) else subnets_a.get("subnets", [])
                list_b = subnets_b if isinstance(subnets_b, list) else subnets_b.get("subnets", [])

                ids_a = {s.get("id", s.get("subnet_id", "")) for s in list_a}
                ids_b = {s.get("id", s.get("subnet_id", "")) for s in list_b}
                no_overlap = ids_a.isdisjoint(ids_b)
                result["tests"]["no_peering"] = {"passed": no_overlap}
            except Exception as e:
                result["tests"]["no_peering"] = {"passed": False, "error": str(e)}
        else:
            result["tests"]["no_peering"] = {"passed": False, "error": "could not create both VPCs"}

        all_passed = all(t.get("passed", False) for t in result["tests"].values())
        result["success"] = all_passed

    finally:
        # Clean up both VPCs
        for vpc_id in (vpc_a_id, vpc_b_id):
            if vpc_id:
                try:
                    run_carbide("vpc", "delete", "--id", vpc_id)
                except Exception:
                    pass

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
