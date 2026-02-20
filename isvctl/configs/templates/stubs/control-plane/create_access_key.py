#!/usr/bin/env python3
"""Create a test user and generate an access key / API token.

Provider-agnostic template — replace the TODO section with your platform's
identity management calls (e.g. Keystone, IAM, service accounts, etc.).

Required JSON output:
{
    "success":          bool — true if user and key created,
    "platform":         str  — "control_plane",
    "username":         str  — name of the created test user,
    "access_key_id":    str  — public credential identifier,
    "secret_access_key": str — secret credential value
}

Usage:
    python create_access_key.py --region us-west-2

AWS reference implementation:
    ../../../stubs/aws/control-plane/create_access_key.py
"""

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Create test user and access key")
    parser.add_argument("--region", required=True, help="Cloud region / availability zone")
    _args = parser.parse_args()

    result: dict = {
        "success": False,
        "platform": "control_plane",
        "username": "",
        "access_key_id": "",
        "secret_access_key": "",
    }

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  TODO: Replace this block with your platform's implementation    ║
    # ║                                                                  ║
    # ║  1. Create a test user / service account                         ║
    # ║     → result["username"] = "<created-username>"                  ║
    # ║  2. Generate an access key or API token for the user             ║
    # ║     → result["access_key_id"]     = "<key-id>"                   ║
    # ║     → result["secret_access_key"] = "<secret>"                   ║
    # ║  3. Set result["success"] = True                                 ║
    # ╚══════════════════════════════════════════════════════════════════╝

    result["error"] = "Not implemented - replace with your platform's access key creation logic"

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
