#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Delete VPC in Carbide (teardown for tenant lifecycle).

Usage:
    python delete_tenant.py --group-name ncp-vpc-1234567890

Output JSON:
{
    "success": true,
    "platform": "control_plane",
    "resources_deleted": ["vpc/<id>"]
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
    parser = argparse.ArgumentParser(description="Delete Carbide VPC")
    parser.add_argument("--group-name", default="", help="VPC name (unused, ID from state)")
    parser.add_argument("--region", default=os.environ.get("CARBIDE_REGION", "us-west-2"))
    parser.add_argument("--skip-destroy", action="store_true")
    args = parser.parse_args()

    result: dict[str, Any] = {"success": False, "platform": "control_plane"}

    if args.skip_destroy:
        result["success"] = True
        result["skipped"] = True
        print(json.dumps(result, indent=2))
        return 0

    state = load_state()
    vpc_id = state.get("vpc_id", "")

    if not state.get("vpc_created", True):
        # Pre-existing VPC — don't delete
        result["success"] = True
        result["skipped"] = True
        result["message"] = f"VPC {vpc_id} is pre-existing, not deleting"
        result["resources_deleted"] = []
        print(json.dumps(result, indent=2))
        return 0

    try:
        run_carbide("vpc", "delete", "--id", vpc_id)
        result["resources_deleted"] = [f"vpc/{vpc_id}"]
        result["success"] = True
    except RuntimeError as e:
        if "not found" in str(e).lower() or "404" in str(e):
            result["resources_deleted"] = [f"vpc/{vpc_id}"]
            result["success"] = True
            result["already_deleted"] = True
        else:
            result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
