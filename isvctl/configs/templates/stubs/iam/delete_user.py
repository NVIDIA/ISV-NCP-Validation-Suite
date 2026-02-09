#!/usr/bin/env python3
"""Delete user account - TEMPLATE (replace with your platform implementation).

This script is called during the "teardown" phase. It must:
  1. Clean up any credentials / tokens for the user
  2. Delete the user account
  3. Print a JSON object to stdout

Required JSON output fields:
  {
    "success": true,                     # boolean - did the delete succeed?
    "platform": "iam",                   # string  - always "iam"
    "resources_deleted": ["user:name"],  # list    - what was cleaned up
    "message": "User deleted"            # string  - human-readable status
  }

On failure, set "success": false and include an "error" field.
If the user doesn't exist, return success (idempotent teardown).

Usage:
    python delete_user.py --username test-user-abc123
    python delete_user.py --username test-user-abc123 --skip-destroy

Reference implementation: ../../../stubs/aws/iam/delete_user.py
"""

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Delete IAM user (template)")
    parser.add_argument("--username", required=True, help="Username to delete")
    parser.add_argument("--skip-destroy", action="store_true", help="Skip actual deletion")
    args = parser.parse_args()

    result: dict = {
        "success": False,
        "platform": "iam",
        "resources_deleted": [],
        "message": "",
    }

    if args.skip_destroy:
        result["success"] = True
        result["message"] = "Destroy skipped (--skip-destroy flag)"
        print(json.dumps(result, indent=2))
        return 0

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  TODO: Replace this block with your platform's user deletion   ║
    # ║                                                                ║
    # ║  Example (pseudocode):                                         ║
    # ║    client = MyIamClient(api_url=os.environ["IAM_API_URL"])     ║
    # ║    client.revoke_all_keys(username=args.username)              ║
    # ║    client.delete_user(username=args.username)                  ║
    # ║    result["resources_deleted"].append(f"user:{args.username}") ║
    # ║    result["success"] = True                                    ║
    # ║    result["message"] = "User deleted successfully"             ║
    # ║                                                                ║
    # ║  If user not found, still return success (idempotent):         ║
    # ║    result["success"] = True                                    ║
    # ║    result["message"] = "User not found (already deleted)"      ║
    # ╚══════════════════════════════════════════════════════════════════╝

    result["error"] = "Not implemented - replace with your platform's user deletion logic"
    print(json.dumps(result, indent=2))
    return 1


if __name__ == "__main__":
    sys.exit(main())
