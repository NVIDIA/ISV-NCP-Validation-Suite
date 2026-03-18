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
    "success": true,          # boolean - did the operation succeed?
    "platform": "iam",        # string  - always "iam"
    "username": "...",         # string  - the created username
    "user_id":  "...",         # string  - unique user identifier
    "access_key_id": "...",   # string  - credential identifier (optional)
    "secret_access_key": "..."# string  - credential secret (optional)
  }

On failure, set "success": false and include an "error" field:
  {
    "success": false,
    "platform": "iam",
    "error": "descriptive error message"
  }

Usage:
    python create_user.py --username isv-test-user

Reference implementation: ../aws/iam/create_user.py
"""

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Create IAM user (template)")
    parser.add_argument("--username", default="isv-test-user", help="Username to create")
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
    # ║    result["access_key_id"] = user.api_key_id                     ║
    # ║    result["secret_access_key"] = user.api_key_secret             ║
    # ║    result["success"] = True                                      ║
    # ╚══════════════════════════════════════════════════════════════════╝

    result["error"] = "Not implemented - replace with your platform's user creation logic"
    print(json.dumps(result, indent=2))

    # Return 0 if success, non-zero if failure
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
