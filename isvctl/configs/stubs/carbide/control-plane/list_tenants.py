#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""List VPCs in Carbide (maps to template's "list tenants" step).

Usage:
    python list_tenants.py --target-group ncp-vpc-1234567890

Output JSON:
{
    "success": true,
    "platform": "control_plane",
    "tenants": [{"tenant_name": "...", "tenant_id": "..."}],
    "count": 1,
    "found_target": true,
    "target_tenant": "ncp-vpc-1234567890"
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
    parser = argparse.ArgumentParser(description="List Carbide VPCs")
    parser.add_argument("--region", default=os.environ.get("CARBIDE_REGION", "us-west-2"))
    parser.add_argument("--target-group", default="", help="VPC name to verify exists")
    args = parser.parse_args()

    state = load_state()
    target = args.target_group or state.get("vpc_name", "")

    result: dict[str, Any] = {
        "success": False,
        "platform": "control_plane",
        "tenants": [],
    }

    try:
        resp = run_carbide("vpc", "list")
        vpcs = resp if isinstance(resp, list) else resp.get("items", [])

        for vpc in vpcs:
            result["tenants"].append({
                "tenant_name": vpc.get("name", ""),
                "tenant_id": vpc.get("id", vpc.get("vpc_id", "")),
            })

        result["count"] = len(result["tenants"])

        if target:
            result["target_tenant"] = target
            result["found_target"] = any(
                t["tenant_name"] == target for t in result["tenants"]
            )

        result["success"] = True

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
