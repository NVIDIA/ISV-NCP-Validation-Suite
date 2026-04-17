#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""List tenants / resource groups and verify a target exists.

Provider-agnostic template — replace the TODO section with your platform's
multi-tenancy listing calls.

Required JSON output (field names must match — TenantListedCheck reads these):
{
    "success":       bool                               — true if listing succeeded,
    "platform":      str                                — "control_plane",
    "tenants":       list[{tenant_name, tenant_id}]     — list of tenant objects,
    "count":         int                                — len(tenants),
    "target_tenant": str                                — echoes --target-group,
    "found_target":  bool                               — true if target is in the list,
    "error":         str                                — error message (present when success is false)
}

Usage:
    python list_tenants.py --region <region> --target-group my-tenant

AWS reference implementation:
    ../aws/control-plane/list_tenants.py
"""

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="List tenants / resource groups")
    parser.add_argument("--region", required=True, help="Cloud region / availability zone")
    parser.add_argument("--target-group", required=True, help="Tenant name to look for")
    args = parser.parse_args()

    result: dict = {
        "success": False,
        "platform": "control_plane",
        "tenants": [],
        "count": 0,
        "target_tenant": args.target_group,
        "found_target": False,
    }

    # ╔══════════════════════════════════════════════════════════════════════════╗
    # ║  TODO: Replace this block with your platform's implementation           ║
    # ║                                                                         ║
    # ║  1. List all tenants / resource groups / projects                       ║
    # ║     → result["tenants"] = [{"tenant_name": "...", "tenant_id": "..."}]  ║
    # ║     → result["count"]   = len(result["tenants"])                        ║
    # ║  2. Check if args.target_group is in the list                           ║
    # ║     → result["found_target"] = True / False                             ║
    # ║  3. Set result["success"] = True                                        ║
    # ╚══════════════════════════════════════════════════════════════════════════╝

    result["tenants"] = [{"tenant_name": args.target_group, "tenant_id": "dummy-tenant-id"}]
    result["count"] = len(result["tenants"])
    result["found_target"] = True
    result["success"] = True

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
