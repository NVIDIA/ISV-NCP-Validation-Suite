#!/usr/bin/env python3
"""Verify that a disabled access key is rejected on authentication.

Provider-agnostic template — replace the TODO section with your platform's
credential verification calls. This script should EXPECT authentication to
fail; success means the key was properly rejected.

Required JSON output:
{
    "success":    bool — true if the disabled key was correctly rejected,
    "platform":   str  — "control_plane",
    "rejected":   bool — true if authentication was denied,
    "error_type": str  — category of rejection (e.g. "InvalidClientTokenId"),
    "error":      str  — (optional) error message, present when success is false
}

Usage:
    python verify_key_rejected.py --access-key-id AKID --secret-access-key SECRET --region us-west-2

AWS reference implementation:
    ../../../stubs/aws/control-plane/verify_key_rejected.py
"""

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify disabled key is rejected")
    parser.add_argument("--access-key-id", required=True, help="Disabled key to test")
    parser.add_argument("--secret-access-key", required=True, help="Secret for the disabled key")
    parser.add_argument("--region", required=True, help="Cloud region / availability zone")
    args = parser.parse_args()  # noqa: F841 — used in TODO block below

    result: dict = {
        "success": False,
        "platform": "control_plane",
        "rejected": False,
        "error_type": "",
    }

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  TODO: Replace this block with your platform's implementation    ║
    # ║                                                                  ║
    # ║  1. Attempt to authenticate using the disabled credentials       ║
    # ║     (args.access_key_id, args.secret_access_key)                 ║
    # ║  2. If authentication FAILS (expected):                          ║
    # ║     → result["rejected"]   = True                                ║
    # ║     → result["error_type"] = "<rejection-error-code>"            ║
    # ║     → result["success"]    = True                                ║
    # ║  3. If authentication SUCCEEDS (unexpected — key not disabled):  ║
    # ║     → result["rejected"]   = False                               ║
    # ║     → result["error"]      = "Key was not rejected"              ║
    # ╚══════════════════════════════════════════════════════════════════╝

    result["error"] = "Not implemented - replace with your platform's key rejection verification logic"

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
