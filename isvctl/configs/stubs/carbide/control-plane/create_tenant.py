#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Create or reuse a VPC in Carbide (maps to template's "tenant" concept).

If ``CARBIDE_VPC_ID`` is set, uses the pre-existing VPC instead of creating
a new one. Only VPCs created by this script are deleted during teardown.

Requires a site ID when creating, provided via ``--site-id`` or the
``CARBIDE_SITE_ID`` environment variable.

Usage:
    python create_tenant.py --site-id <site-id>
    CARBIDE_VPC_ID=<uuid> python create_tenant.py

Output JSON:
{
    "success": true,
    "platform": "control_plane",
    "tenant_name": "ncp-vpc-<ts>",
    "tenant_id": "<vpc-id>",
    "description": "NCP validation VPC"
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
    parser = argparse.ArgumentParser(description="Create Carbide VPC")
    parser.add_argument("--region", default=os.environ.get("CARBIDE_REGION", "us-west-2"))
    parser.add_argument("--name-prefix", default="ncp-vpc")
    parser.add_argument("--site-id", default=os.environ.get("CARBIDE_SITE_ID", ""))
    parser.add_argument("--vpc-id", default=os.environ.get("CARBIDE_VPC_ID", ""))
    args = parser.parse_args()

    result: dict[str, Any] = {
        "success": False,
        "platform": "control_plane",
    }

    try:
        state = load_state()

        if args.vpc_id:
            # Use pre-existing VPC
            resp = run_carbide("vpc", "get", args.vpc_id)
            vpc_id = resp.get("id", args.vpc_id)
            vpc_name = resp.get("name", args.vpc_id)
            state["vpc_created"] = False
        else:
            # Create new VPC
            if not args.site_id:
                result["error"] = "site-id is required when not using pre-existing VPC"
                print(json.dumps(result, indent=2))
                return 1

            vpc_name = f"{args.name_prefix}-{int(time.time())}"
            resp = run_carbide(
                "vpc", "create",
                "--name", vpc_name,
                "--description", "NCP validation VPC",
                "--site-id", args.site_id,
            )
            vpc_id = resp.get("id", resp.get("vpc_id", ""))
            state["vpc_created"] = True

        result["tenant_name"] = vpc_name
        result["tenant_id"] = vpc_id
        result["description"] = "NCP validation VPC"
        result["success"] = True

        state["vpc_id"] = vpc_id
        state["vpc_name"] = vpc_name
        state["site_id"] = args.site_id
        save_state(state)

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
