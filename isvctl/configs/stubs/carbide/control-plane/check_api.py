#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Check Carbide API connectivity and health.

Verifies the Carbide control plane is reachable by running
``carbidecli tenant get`` and ``carbidecli site list``.

Usage:
    python check_api.py --region us-west-2

Output JSON:
{
    "success": true,
    "platform": "control_plane",
    "account_id": "<tenant-id>",
    "tests": {
        "tenant": {"passed": true, "latency_ms": 123},
        "sites": {"passed": true, "latency_ms": 89}
    }
}
"""

import argparse
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common.carbide import timed_call


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Carbide API health")
    parser.add_argument("--region", default=os.environ.get("CARBIDE_REGION", "us-west-2"))
    parser.add_argument("--services", default="tenant,sites", help="Comma-separated checks")
    args = parser.parse_args()

    result: dict[str, Any] = {
        "success": False,
        "platform": "control_plane",
        "tests": {},
    }

    try:
        # Test tenant get
        tenant_data, tenant_latency = timed_call("tenant", "get")
        result["tests"]["tenant"] = {
            "passed": True,
            "latency_ms": round(tenant_latency * 1000, 2),
        }
        # Extract tenant/account ID from response
        result["account_id"] = tenant_data.get("id", tenant_data.get("tenant_id", ""))

        # Test site list
        sites_data, sites_latency = timed_call("site", "list")
        result["tests"]["sites"] = {
            "passed": True,
            "latency_ms": round(sites_latency * 1000, 2),
        }

        passed = sum(1 for t in result["tests"].values() if t.get("passed", False))
        total = len(result["tests"])
        result["summary"] = f"{passed}/{total} checks passed"
        result["success"] = True

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
