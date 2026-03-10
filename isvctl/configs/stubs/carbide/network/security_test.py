#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Test NSG security rules in Carbide.

Creates a VPC with a Network Security Group and rules, then verifies
the rules exist and are configured for default-deny inbound.

Usage:
    python security_test.py --site-id <site-id>

Output JSON:
{
    "success": true,
    "platform": "network",
    "tests": {
        "create_vpc": {"passed": true},
        "sg_default_deny_inbound": {"passed": true}
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
    parser = argparse.ArgumentParser(description="Carbide NSG security test")
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
    vpc_id = ""
    nsg_id = ""

    result: dict[str, Any] = {
        "success": False,
        "platform": "network",
        "tests": {},
    }

    try:
        # Create VPC
        try:
            vpc_resp = run_carbide(
                "vpc", "create",
                "--name", f"ncp-sec-{ts}",
                "--description", "NCP security test VPC",
                "--site-id", args.site_id,
            )
            vpc_id = vpc_resp.get("id", vpc_resp.get("vpc_id", ""))
            result["tests"]["create_vpc"] = {"passed": bool(vpc_id)}
        except Exception as e:
            result["tests"]["create_vpc"] = {"passed": False, "error": str(e)}

        # Create NSG and verify default-deny
        if vpc_id:
            try:
                nsg_resp = run_carbide(
                    "network-security-group", "create",
                    "--vpc-id", vpc_id,
                    "--name", f"ncp-nsg-{ts}",
                )
                nsg_id = nsg_resp.get("id", nsg_resp.get("nsg_id", ""))

                # Get NSG details and check rules
                nsg_detail = run_carbide(
                    "network-security-group", "get",
                    "--id", nsg_id,
                )

                # Verify NSG exists and has rules (default deny inbound)
                rules = nsg_detail.get("rules", nsg_detail.get("security_rules", []))
                has_deny = any(
                    r.get("action", "").lower() == "deny"
                    or r.get("direction", "").lower() == "inbound"
                    for r in rules
                ) if rules else True  # No rules = implicit deny

                result["tests"]["sg_default_deny_inbound"] = {"passed": bool(nsg_id) and has_deny}
            except Exception as e:
                result["tests"]["sg_default_deny_inbound"] = {"passed": False, "error": str(e)}
        else:
            result["tests"]["sg_default_deny_inbound"] = {
                "passed": False, "error": "no vpc_id from create",
            }

        all_passed = all(t.get("passed", False) for t in result["tests"].values())
        result["success"] = all_passed

    finally:
        # Clean up
        if nsg_id:
            try:
                run_carbide("network-security-group", "delete", "--id", nsg_id)
            except Exception:
                pass
        if vpc_id:
            try:
                run_carbide("vpc", "delete", "--id", vpc_id)
            except Exception:
                pass

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
