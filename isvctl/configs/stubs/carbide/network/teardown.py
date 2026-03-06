#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Tear down all Carbide network resources created during validation.

Deletes subnets, VPC prefixes, NSGs, and VPCs tracked in state.

Usage:
    python teardown.py --site-id <site-id>

Output JSON:
{
    "success": true,
    "platform": "network",
    "resources_deleted": ["subnet/<id>", "vpc-prefix/<id>", "vpc/<id>"]
}
"""

import argparse
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common.carbide import load_state, run_carbide, save_state


def _safe_delete(resource_type: str, resource_id: str) -> bool:
    """Attempt to delete a resource, returning True on success or already-deleted."""
    if not resource_id:
        return False
    try:
        run_carbide(resource_type, "delete", "--id", resource_id)
        return True
    except RuntimeError as e:
        if "not found" in str(e).lower() or "404" in str(e):
            return True
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Carbide network teardown")
    parser.add_argument("--region", default=os.environ.get("CARBIDE_REGION", "us-west-2"))
    parser.add_argument("--site-id", default=os.environ.get("CARBIDE_SITE_ID", ""))
    parser.add_argument("--skip-destroy", action="store_true")
    args = parser.parse_args()

    result: dict[str, Any] = {
        "success": False,
        "platform": "network",
        "resources_deleted": [],
    }

    if args.skip_destroy:
        result["success"] = True
        result["skipped"] = True
        print(json.dumps(result, indent=2))
        return 0

    state = load_state()

    # Delete subnets first (must be removed before VPC)
    for subnet_id in state.get("network_subnet_ids", []):
        if _safe_delete("subnet", subnet_id):
            result["resources_deleted"].append(f"subnet/{subnet_id}")

    # Delete NSGs
    for nsg_id in state.get("network_nsg_ids", []):
        if _safe_delete("network-security-group", nsg_id):
            result["resources_deleted"].append(f"nsg/{nsg_id}")

    # Delete VPC prefix
    prefix_id = state.get("network_prefix_id", "")
    if _safe_delete("vpc-prefix", prefix_id):
        result["resources_deleted"].append(f"vpc-prefix/{prefix_id}")

    # Delete VPC
    vpc_id = state.get("network_vpc_id", "")
    if _safe_delete("vpc", vpc_id):
        result["resources_deleted"].append(f"vpc/{vpc_id}")

    # Clean up state keys
    for key in ("network_vpc_id", "network_vpc_name", "network_prefix_id",
                "network_subnet_ids", "network_nsg_ids"):
        state.pop(key, None)
    save_state(state)

    result["success"] = True

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
