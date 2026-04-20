#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Get detailed information about a specific tenant / resource group.

Provider-agnostic template — replace the TODO section with your platform's
tenant detail retrieval calls.

Required JSON output:
{
    "success":     bool — true if tenant info retrieved,
    "platform":    str  — "control_plane",
    "tenant_name": str  — human-readable name,
    "tenant_id":   str  — unique identifier,
    "description": str  — tenant description or metadata,
    "error":       str  — (optional) error message, present when success is false
}

Usage:
    python get_tenant.py --group-name my-tenant --region <region>

AWS reference implementation:
    ../aws/control-plane/get_tenant.py
"""

import argparse
import json
import os
import sys

# ISVCTL_DEMO_MODE=1 enables demo-success output (used by `make smoke-test`).
DEMO_MODE = os.environ.get("ISVCTL_DEMO_MODE") == "1"


def main() -> int:
    parser = argparse.ArgumentParser(description="Get tenant / resource group details")
    parser.add_argument("--group-name", required=True, help="Tenant / group name to look up")
    parser.add_argument("--region", required=True, help="Cloud region / availability zone")
    args = parser.parse_args()

    result: dict = {
        "success": False,
        "platform": "control_plane",
        "tenant_name": "",
        "tenant_id": "",
        "description": "",
    }

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  TODO: Replace this block with your platform's implementation    ║
    # ║                                                                  ║
    # ║  1. Fetch details for the tenant named args.group_name           ║
    # ║     → result["tenant_name"] = "<name>"                           ║
    # ║     → result["tenant_id"]   = "<id>"                             ║
    # ║     → result["description"] = "<description or metadata>"        ║
    # ║  2. Set result["success"] = True                                 ║
    # ╚══════════════════════════════════════════════════════════════════╝

    if DEMO_MODE:
        result["tenant_name"] = args.group_name
        result["tenant_id"] = "dummy-tenant-id"
        result["description"] = "Dummy tenant for living example"
        result["success"] = True
    else:
        result["error"] = "Not implemented - replace with your platform's tenant detail retrieval logic"

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
