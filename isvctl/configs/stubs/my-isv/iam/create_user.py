#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Create user account - TEMPLATE (replace with your platform implementation).

This script is called during the "setup" phase. It must:
  1. Create a user on your IAM platform
  2. Optionally create credentials (access key / API token)
  3. Print a JSON object to stdout

Required JSON output fields:
  {
    "success": true,           # boolean - did the operation succeed?
    "platform": "iam",         # string  - always "iam"
    "username": "...",         # string  - the created username
    "user_id":  "...",         # string  - unique user identifier
    "access_key_id": "...",    # string  - credential identifier (optional)
    "secret_access_key": "..." # string  - credential secret (optional)
  }

On failure, set "success": false and include an "error" field:
  {
    "success": false,
    "platform": "iam",
    "error": "descriptive error message"
  }

Usage:
    python create_user.py --username isv-test-user --create-access-key

Reference implementation: ../../aws/iam/create_user.py
"""

import argparse
import json
import os
import sys

# ISVCTL_DEMO_MODE=1 enables demo-success output (used by `make smoke-test`).
DEMO_MODE = os.environ.get("ISVCTL_DEMO_MODE") == "1"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create IAM user (template)")
    parser.add_argument("--username", default="isv-test-user", help="Username to create")
    parser.add_argument(
        "--create-access-key",
        action="store_true",
        default=False,
        help="Also create credentials for the user (store_true: only enabled when flag is passed)",
    )
    args = parser.parse_args()

    result: dict = {
        "success": False,
        "platform": "iam",
        "username": args.username,
    }

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  TODO: Replace this block with your platform's user creation     ║
    # ║                                                                  ║
    # ║  Example (pseudocode):                                           ║
    # ║    client = MyIamClient(api_url=os.environ["IAM_API_URL"])       ║
    # ║    user = client.create_user(username=args.username)             ║
    # ║    result["user_id"] = user.id                                   ║
    # ║    if args.create_access_key:                                    ║
    # ║        key = client.create_access_key(username)                  ║
    # ║        result["access_key_id"] = key.id                          ║
    # ║        result["secret_access_key"] = key.secret                  ║
    # ║    result["success"] = True                                      ║
    # ╚══════════════════════════════════════════════════════════════════╝

    if DEMO_MODE:
        # Demo-success output for the validation-contract smoke test.
        # Safe to delete once the TODO above is filled in for real.
        result["user_id"] = "dummy-id"
        if args.create_access_key:
            result["access_key_id"] = "dummy-key"
            result["secret_access_key"] = "dummy-secret"
        result["success"] = True
    else:
        result["error"] = "Not implemented - replace with your platform's user creation logic"

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
