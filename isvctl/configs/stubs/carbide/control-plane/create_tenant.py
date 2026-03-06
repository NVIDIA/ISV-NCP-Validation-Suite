#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Create a VPC in Carbide (maps to template's "tenant" concept).

Requires a site ID, provided via ``--site-id`` or the
``CARBIDE_SITE_ID`` environment variable.

Usage:
    python create_tenant.py --site-id <site-id>

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
    args = parser.parse_args()

    if not args.site_id:
        print(json.dumps({
            "success": False,
            "platform": "control_plane",
            "error": "site-id is required (--site-id or CARBIDE_SITE_ID env var)",
        }, indent=2))
        return 1

    vpc_name = f"{args.name_prefix}-{int(time.time())}"
    description = "NCP validation VPC"

    result: dict[str, Any] = {
        "success": False,
        "platform": "control_plane",
        "tenant_name": vpc_name,
    }

    try:
        resp = run_carbide(
            "vpc", "create",
            "--name", vpc_name,
            "--description", description,
            "--site-id", args.site_id,
        )
        vpc_id = resp.get("id", resp.get("vpc_id", ""))

        result["tenant_id"] = vpc_id
        result["description"] = description
        result["success"] = True

        # Persist for subsequent steps
        state = load_state()
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
