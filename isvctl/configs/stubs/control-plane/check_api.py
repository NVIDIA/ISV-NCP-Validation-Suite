#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Check cloud API connectivity and health.

Provider-agnostic template — replace the TODO section with your platform's
API client calls (e.g. OpenStack SDK, GCP client, Azure SDK, etc.).

Required JSON output:
{
    "success":    bool   — true if authentication and at least core services reachable,
    "platform":   str    — "control_plane",
    "account_id": str    — authenticated identity / account / project ID,
    "tests": {
        "auth":          {"passed": bool},
        "<service_name>": {"passed": bool}
        ...one entry per service checked...
    },
    "error": str — (optional) error message, present when success is false
}

Usage:
    python check_api.py --region <region> --services compute,storage,identity

AWS reference implementation:
    ../aws/control-plane/check_api.py
"""

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Check cloud API health")
    parser.add_argument("--region", required=True, help="Cloud region / availability zone")
    parser.add_argument(
        "--services",
        default="compute,storage,identity",
        help="Comma-separated list of services to probe",
    )
    args = parser.parse_args()

    _services = [s.strip() for s in args.services.split(",")]

    result: dict = {
        "success": False,
        "platform": "control_plane",
        "account_id": "",
        "tests": {},
    }

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  TODO: Replace this block with your platform's implementation    ║
    # ║                                                                  ║
    # ║  1. Authenticate to your cloud API (SDK client, token, etc.)     ║
    # ║  2. Retrieve the caller identity / account ID                    ║
    # ║     → result["account_id"] = "<your-account-id>"                 ║
    # ║  3. For each service in `services`:                              ║
    # ║     a. Call a lightweight read-only endpoint                     ║
    # ║     b. Record the result:                                        ║
    # ║        result["tests"]["<service>"] = {"passed": True/False}     ║
    # ║  4. Set result["success"] = True if auth passed                  ║
    # ╚══════════════════════════════════════════════════════════════════╝

    result["account_id"] = "dummy-account-123"
    for service in _services:
        result["tests"][service] = {"passed": True}
    result["tests"]["auth"] = {"passed": True}
    result["success"] = True

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
