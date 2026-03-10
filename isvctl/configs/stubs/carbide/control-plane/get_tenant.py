#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Get VPC details from Carbide (maps to template's "get tenant" step).

Usage:
    python get_tenant.py --group-name ncp-vpc-1234567890

Output JSON:
{
    "success": true,
    "platform": "control_plane",
    "tenant_name": "ncp-vpc-1234567890",
    "tenant_id": "<vpc-id>",
    "description": "NCP validation VPC"
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
    parser = argparse.ArgumentParser(description="Get Carbide VPC details")
    parser.add_argument("--group-name", default="", help="VPC name (or loaded from state)")
    parser.add_argument("--region", default=os.environ.get("CARBIDE_REGION", "us-west-2"))
    args = parser.parse_args()

    state = load_state()
    vpc_id = state.get("vpc_id", "")
    vpc_name = args.group_name or state.get("vpc_name", "")

    result: dict[str, Any] = {
        "success": False,
        "platform": "control_plane",
        "tenant_name": vpc_name,
    }

    try:
        resp = run_carbide("vpc", "get", "--id", vpc_id)

        result["tenant_id"] = resp.get("id", resp.get("vpc_id", ""))
        result["tenant_name"] = resp.get("name", vpc_name)
        result["description"] = resp.get("description", "NCP validation VPC")
        result["success"] = True

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
