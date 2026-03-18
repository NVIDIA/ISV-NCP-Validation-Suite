#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Delete an access key and its associated test user.

Provider-agnostic template — replace the TODO section with your platform's
credential and user cleanup calls.

Required JSON output:
{
    "success":           bool      — true if cleanup succeeded,
    "platform":          str       — "control_plane",
    "resources_deleted": list[str] — names/IDs of deleted resources,
    "message":           str       — human-readable summary,
    "error":             str       — (optional) error message, present when success is false
}

Usage:
    python delete_access_key.py --username testuser --access-key-id AKID

AWS reference implementation:
    ../aws/control-plane/delete_access_key.py
"""

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Delete access key and test user")
    parser.add_argument("--username", required=True, help="User who owns the key")
    parser.add_argument("--access-key-id", required=True, help="Key to delete")
    args = parser.parse_args()  # noqa: F841 — used in TODO block below

    result: dict = {
        "success": False,
        "platform": "control_plane",
        "resources_deleted": [],
        "message": "",
    }

    # ╔══════════════════════════════════════════════════════════════════════════╗
    # ║  TODO: Replace this block with your platform's implementation           ║
    # ║                                                                         ║
    # ║  Available arguments:                                                   ║
    # ║    args.username       — user who owns the key                          ║
    # ║    args.access_key_id  — key to delete                                  ║
    # ║                                                                         ║
    # ║  1. Delete the access key / API token                                   ║
    # ║     → result["resources_deleted"].append(f"access_key:{args.access_key_id}")  ║
    # ║  2. Delete the test user / service account                              ║
    # ║     → result["resources_deleted"].append(f"user:{args.username}")        ║
    # ║  3. Set result["message"] and result["success"] = True                  ║
    # ╚══════════════════════════════════════════════════════════════════════════╝

    result["error"] = "Not implemented - replace with your platform's access key deletion logic"

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
