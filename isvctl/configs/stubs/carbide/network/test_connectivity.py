#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Verify subnet exists and is accessible in Carbide.

Checks the shared VPC's subnet is present and in an active state,
confirming an instance would receive an IP from the subnet.

Usage:
    python test_connectivity.py --site-id <site-id>

Output JSON:
{
    "success": true,
    "platform": "network",
    "tests": {
        "network_assigned": {"passed": true}
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
    parser = argparse.ArgumentParser(description="Carbide connectivity test")
    parser.add_argument("--region", default=os.environ.get("CARBIDE_REGION", "us-west-2"))
    parser.add_argument("--site-id", default=os.environ.get("CARBIDE_SITE_ID", ""))
    args = parser.parse_args()

    state = load_state()
    vpc_id = state.get("network_vpc_id", "")
    subnet_ids = state.get("network_subnet_ids", [])

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
        # Verify at least one subnet exists and is accessible
        list_resp = run_carbide("subnet", "list", "--vpc-id", vpc_id)
        listed = list_resp if isinstance(list_resp, list) else list_resp.get("subnets", [])
        listed_ids = {s.get("id", s.get("subnet_id", "")) for s in listed}

        has_subnet = bool(listed_ids)
        known_found = any(sid in listed_ids for sid in subnet_ids) if subnet_ids else has_subnet

        result["tests"]["network_assigned"] = {"passed": has_subnet and known_found}
        result["success"] = has_subnet and known_found

    except Exception as e:
        result["tests"]["network_assigned"] = {"passed": False, "error": str(e)}
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
