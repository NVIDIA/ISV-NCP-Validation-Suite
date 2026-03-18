#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Test user credentials - TEMPLATE (replace with your platform implementation).

This script is called during the "test" phase. It must:
  1. Use the credentials from create_user to authenticate
  2. Verify the identity / make a test API call
  3. Print a JSON object to stdout

Required JSON output fields:
  {
    "success": true,           # boolean - did the overall test pass?
    "platform": "iam",         # string  - always "iam"
    "account_id": "...",       # string  - account/tenant identifier
    "tests": {                 # object  - individual test results
      "identity": {"passed": true},
      "access":   {"passed": true, "note": "optional detail"}
    }
  }

On failure, set "success": false and include an "error" field.

Usage:
    python test_credentials.py --username test-user \\
        --credential-id AKID... --credential-secret SECRET...

Reference implementation: ../aws/iam/test_credentials.py
"""

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Test IAM credentials (template)")
    parser.add_argument("--username", required=True, help="Username to test")
    parser.add_argument("--credential-id", required=True, help="Credential / API key ID")
    parser.add_argument("--credential-secret", required=True, help="Credential secret")
    args = parser.parse_args()  # noqa: F841

    result: dict = {
        "success": False,
        "platform": "iam",
        "account_id": "",
        "tests": {},
    }

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  TODO: Replace this block with your platform's auth test         ║
    # ║                                                                  ║
    # ║  Example (pseudocode):                                           ║
    # ║    session = MyIamClient(                                        ║
    # ║        key_id=args.credential_id,                                ║
    # ║        secret=args.credential_secret,                            ║
    # ║    )                                                             ║
    # ║    identity = session.whoami()                                   ║
    # ║    result["account_id"] = identity.account_id                    ║
    # ║    result["tests"]["identity"] = {"passed": True}                ║
    # ║    result["tests"]["access"] = {"passed": True}                  ║
    # ║    result["success"] = True                                      ║
    # ╚══════════════════════════════════════════════════════════════════╝

    result["error"] = "Not implemented - replace with your platform's credential test logic"
    print(json.dumps(result, indent=2))

    # Return 0 if success, non-zero if failure
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
