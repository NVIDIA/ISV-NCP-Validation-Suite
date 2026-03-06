#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Simplified traffic validation for Carbide.

Verifies VPC and subnet routing configuration is correct by confirming
the VPC exists and subnets are properly associated.

Usage:
    python traffic_test.py --site-id <site-id>

Output JSON:
{
    "success": true,
    "platform": "network",
    "tests": {
        "network_setup": {"passed": true}
    }
}
"""

import argparse
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common.carbide import load_state, run_carbide


def main() -> int:
    parser = argparse.ArgumentParser(description="Carbide traffic validation")
    parser.add_argument("--region", default=os.environ.get("CARBIDE_REGION", "us-west-2"))
    parser.add_argument("--site-id", default=os.environ.get("CARBIDE_SITE_ID", ""))
    args = parser.parse_args()

    state = load_state()
    vpc_id = state.get("network_vpc_id", "")

    result: dict[str, Any] = {
        "success": False,
        "platform": "network",
        "tests": {},
    }

    if not vpc_id:
        result["error"] = "no network_vpc_id in state; run create_vpc first"
        print(json.dumps(result, indent=2))
        return 1

    try:
        # Verify VPC exists
        vpc_resp = run_carbide("vpc", "get", "--id", vpc_id)
        got_id = vpc_resp.get("id", vpc_resp.get("vpc_id", ""))

        # Verify subnets are associated
        list_resp = run_carbide("subnet", "list", "--vpc-id", vpc_id)
        listed = list_resp if isinstance(list_resp, list) else list_resp.get("subnets", [])

        vpc_ok = got_id == vpc_id
        subnets_ok = len(listed) > 0

        result["tests"]["network_setup"] = {"passed": vpc_ok and subnets_ok}
        result["success"] = vpc_ok and subnets_ok

    except Exception as e:
        result["tests"]["network_setup"] = {"passed": False, "error": str(e)}
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
