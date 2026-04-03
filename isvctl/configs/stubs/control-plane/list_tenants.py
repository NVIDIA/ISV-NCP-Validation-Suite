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

Required JSON output:
{
    "success":  bool             — true if listing succeeded,
    "platform": str              — "control_plane",
    "tenants":  list[{name, id}] — list of tenant objects,
    "found":    bool             — true if target tenant is in the list,
    "error":    str              — error message (present when success is false)
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
    args = parser.parse_args()  # noqa: F841 — used in TODO block below

    result: dict = {
        "success": False,
        "platform": "control_plane",
        "tenants": [],
        "found": False,
    }

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  TODO: Replace this block with your platform's implementation    ║
    # ║                                                                  ║
    # ║  1. List all tenants / resource groups / projects                ║
    # ║     → result["tenants"] = [{"name": "...", "id": "..."}, ...]    ║
    # ║  2. Check if args.target_group is in the list                    ║
    # ║     → result["found"] = True / False                             ║
    # ║  3. Set result["success"] = True                                 ║
    # ╚══════════════════════════════════════════════════════════════════╝

    result["error"] = "Not implemented - replace with your platform's tenant listing logic"

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
