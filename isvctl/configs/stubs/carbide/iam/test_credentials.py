#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Verify Carbide API scopes against template requirements.

Maps the IAM template's "test_credentials" step. Checks that the
current token has the required scopes for each Carbide template
(control-plane, network, image-registry, bm).

Usage:
    python test_credentials.py

Output JSON:
{
    "success": true,
    "platform": "iam",
    "account_id": "<tenant-id>",
    "tests": {
        "identity": {"passed": true, "message": "..."},
        "scopes_control-plane": {"passed": true, "granted": [...], "missing": []},
        "scopes_network": {"passed": true, ...},
        ...
    }
}
"""

import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common.carbide import (
    TEMPLATE_SCOPES,
    check_scopes,
    effective_scopes_for_template,
    run_carbide,
    timed_call,
)


def main() -> int:
    result: dict[str, Any] = {
        "success": False,
        "platform": "iam",
        "tests": {},
    }

    try:
        # Identity check
        tenant_data, latency = timed_call("tenant", "get")
        result["account_id"] = tenant_data.get("id", "")
        result["tests"]["identity"] = {
            "passed": True,
            "message": f"Authenticated as {tenant_data.get('name', '')}",
            "latency_ms": round(latency * 1000),
        }

        # Read access check
        try:
            run_carbide("site", "list")
            result["tests"]["access"] = {
                "passed": True,
                "message": "Read access verified (site list)",
            }
        except Exception as e:
            result["tests"]["access"] = {
                "passed": False,
                "message": f"Read access failed: {e}",
            }

        # Scope checks per template (accounts for pre-existing resources)
        all_passed = True
        for template_name in TEMPLATE_SCOPES:
            effective = effective_scopes_for_template(template_name)
            ok, granted, missing = check_scopes(effective)
            result["tests"][f"scopes_{template_name}"] = {
                "passed": ok,
                "granted": granted,
                "missing": missing,
                "effective_requirements": {k: v for k, v in effective.items()},
            }
            if not ok:
                all_passed = False

        result["success"] = (
            result["tests"]["identity"]["passed"]
            and result["tests"]["access"]["passed"]
        )
        # Note: scope check failures are warnings, not hard failures.
        # The token works, but some templates may not run.
        if not all_passed:
            result["scope_warnings"] = True

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
