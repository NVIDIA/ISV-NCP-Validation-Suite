#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Delete a tenant / resource group / project.

Provider-agnostic template — replace the TODO section with your platform's
tenant deletion calls.

Required JSON output:
{
    "success":           bool      — true if tenant deleted,
    "platform":          str       — "control_plane",
    "resources_deleted": list[str] — names/IDs of deleted resources,
    "message":           str       — human-readable summary,
    "error":             str       — (optional) human-readable error details, present when success is false
}

Usage:
    python delete_tenant.py --group-name my-tenant --region <region>

AWS reference implementation:
    ../aws/control-plane/delete_tenant.py
"""

import argparse
import json
import os
import sys

# ISVCTL_DEMO_MODE=1 enables demo-success output (used by `make demo-test`).
DEMO_MODE = os.environ.get("ISVCTL_DEMO_MODE") == "1"


def main() -> int:
    parser = argparse.ArgumentParser(description="Delete tenant / resource group")
    parser.add_argument("--group-name", required=True, help="Tenant / group to delete")
    parser.add_argument("--region", required=True, help="Cloud region / availability zone")
    args = parser.parse_args()

    result: dict = {
        "success": False,
        "platform": "control_plane",
        "resources_deleted": [],
        "message": "",
    }

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  TODO: Replace this block with your platform's implementation    ║
    # ║                                                                  ║
    # ║  1. Delete the tenant / resource group / project                 ║
    # ║     → result["resources_deleted"].append("tenant:<name>")        ║
    # ║  2. Set result["message"] and result["success"] = True           ║
    # ╚══════════════════════════════════════════════════════════════════╝

    if DEMO_MODE:
        result["resources_deleted"].append(f"tenant:{args.group_name}")
        result["message"] = "Tenant deleted"
        result["success"] = True

    else:
        result["error"] = "Not implemented - replace with your platform's tenant deletion logic"

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
