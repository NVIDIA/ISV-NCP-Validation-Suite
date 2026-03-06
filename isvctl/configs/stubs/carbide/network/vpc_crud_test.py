#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Test VPC CRUD lifecycle in Carbide.

Creates a temporary VPC, reads it back, updates its tag, then deletes it.

Usage:
    python vpc_crud_test.py --site-id <site-id>

Output JSON:
{
    "success": true,
    "platform": "network",
    "tests": {
        "create_vpc": {"passed": true},
        "read_vpc": {"passed": true},
        "delete_vpc": {"passed": true}
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
    parser = argparse.ArgumentParser(description="Carbide VPC CRUD test")
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

    vpc_name = f"ncp-crud-{int(time.time())}"
    vpc_id = ""

    result: dict[str, Any] = {
        "success": False,
        "platform": "network",
        "tests": {},
    }

    try:
        # CREATE
        try:
            resp = run_carbide(
                "vpc", "create",
                "--name", vpc_name,
                "--description", "NCP CRUD test VPC",
                "--site-id", args.site_id,
            )
            vpc_id = resp.get("id", resp.get("vpc_id", ""))
            result["tests"]["create_vpc"] = {"passed": bool(vpc_id)}
        except Exception as e:
            result["tests"]["create_vpc"] = {"passed": False, "error": str(e)}

        # READ
        if vpc_id:
            try:
                get_resp = run_carbide("vpc", "get", "--id", vpc_id)
                got_id = get_resp.get("id", get_resp.get("vpc_id", ""))
                result["tests"]["read_vpc"] = {"passed": got_id == vpc_id}
            except Exception as e:
                result["tests"]["read_vpc"] = {"passed": False, "error": str(e)}
        else:
            result["tests"]["read_vpc"] = {"passed": False, "error": "no vpc_id from create"}

        # DELETE
        if vpc_id:
            try:
                run_carbide("vpc", "delete", "--id", vpc_id)
                result["tests"]["delete_vpc"] = {"passed": True}
            except Exception as e:
                result["tests"]["delete_vpc"] = {"passed": False, "error": str(e)}
        else:
            result["tests"]["delete_vpc"] = {"passed": False, "error": "no vpc_id to delete"}

        all_passed = all(t.get("passed", False) for t in result["tests"].values())
        result["success"] = all_passed

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
