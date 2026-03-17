#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Disable / deactivate an access key.

Provider-agnostic template — replace the TODO section with your platform's
credential management calls (e.g. set key status to inactive, revoke token).

Required JSON output:
{
    "success":       bool — true if key was disabled,
    "platform":      str  — "control_plane",
    "access_key_id": str  — the key that was disabled,
    "status":        str  — "disabled",
    "error":         str or null — error message when disabling fails; null/absent on success
}

Usage:
    python disable_access_key.py --username testuser --access-key-id AKID

AWS reference implementation:
    ../../../stubs/aws/control-plane/disable_access_key.py
"""

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Disable an access key")
    parser.add_argument("--username", required=True, help="User who owns the key")
    parser.add_argument("--access-key-id", required=True, help="Key to disable")
    args = parser.parse_args()

    result: dict = {
        "success": False,
        "platform": "control_plane",
        "access_key_id": args.access_key_id,
        "status": "",
    }

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  TODO: Replace this block with your platform's implementation    ║
    # ║                                                                  ║
    # ║  1. Disable / deactivate the access key                          ║
    # ║     (e.g. set status to Inactive, revoke the token)              ║
    # ║  2. On success:                                                  ║
    # ║     → result["status"]  = "disabled"                             ║
    # ║     → result["success"] = True                                   ║
    # ╚══════════════════════════════════════════════════════════════════╝

    result["error"] = "Not implemented - replace with your platform's key disable logic"

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
