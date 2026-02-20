#!/usr/bin/env python3
"""Test that a previously created access key can authenticate.

Provider-agnostic template — replace the TODO section with your platform's
credential verification calls.

Required JSON output:
{
    "success":       bool — true if authentication succeeded,
    "platform":      str  — "control_plane",
    "authenticated": bool — true if the key successfully authenticated,
    "account_id":    str  — identity / account returned by the API
}

Usage:
    python test_access_key.py --access-key-id AKID --secret-access-key SECRET --region us-west-2

AWS reference implementation:
    ../../../stubs/aws/control-plane/test_access_key.py
"""

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Test access key authentication")
    parser.add_argument("--access-key-id", required=True, help="Public credential identifier")
    parser.add_argument("--secret-access-key", required=True, help="Secret credential value")
    parser.add_argument("--region", required=True, help="Cloud region / availability zone")
    _args = parser.parse_args()

    result: dict = {
        "success": False,
        "platform": "control_plane",
        "authenticated": False,
        "account_id": "",
    }

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  TODO: Replace this block with your platform's implementation    ║
    # ║                                                                  ║
    # ║  1. Create an API client using the provided credentials          ║
    # ║     (args.access_key_id, args.secret_access_key)                 ║
    # ║  2. Call a "get identity" / "whoami" endpoint                    ║
    # ║  3. On success:                                                  ║
    # ║     → result["authenticated"] = True                             ║
    # ║     → result["account_id"]    = "<returned-account-id>"          ║
    # ║     → result["success"]       = True                             ║
    # ║  4. On failure:                                                  ║
    # ║     → result["authenticated"] = False                            ║
    # ║     → result["error"]         = "<error-message>"                ║
    # ╚══════════════════════════════════════════════════════════════════╝

    result["error"] = "Not implemented - replace with your platform's credential verification logic"

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
