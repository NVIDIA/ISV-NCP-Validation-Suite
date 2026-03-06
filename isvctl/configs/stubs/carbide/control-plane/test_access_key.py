#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Test that the created SSH key is visible in Carbide.

Lists SSH keys and verifies the key created by ``create_access_key``
appears in the listing.

Usage:
    python test_access_key.py --access-key-id <key-id>

Output JSON:
{
    "success": true,
    "platform": "control_plane",
    "authenticated": true,
    "identity_id": "<key-id>",
    "account_id": "<tenant-id>"
}
"""

import argparse
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common.carbide import load_state, run_carbide


def main() -> int:
    parser = argparse.ArgumentParser(description="Test Carbide SSH key visibility")
    parser.add_argument("--access-key-id", default="")
    parser.add_argument("--secret-access-key", default="")
    parser.add_argument("--region", default=os.environ.get("CARBIDE_REGION", "us-west-2"))
    parser.add_argument("--wait", type=int, default=0, help="Seconds to wait (unused)")
    parser.add_argument("--retries", type=int, default=3, help="Number of retry attempts")
    args = parser.parse_args()

    state = load_state()
    key_id = args.access_key_id or state.get("ssh_key_id", "")
    group_id = state.get("ssh_key_group_id", "")

    result: dict[str, Any] = {
        "success": False,
        "platform": "control_plane",
        "authenticated": False,
    }

    try:
        # List SSH keys and look for our key
        keys_resp = run_carbide("ssh-key", "list")
        keys = keys_resp if isinstance(keys_resp, list) else keys_resp.get("items", [])

        found = any(
            k.get("id", k.get("ssh_key_id", "")) == key_id
            for k in keys
        )

        if found:
            result["authenticated"] = True
            result["identity_id"] = key_id
            # Get tenant/account ID
            tenant_resp = run_carbide("tenant", "get")
            result["account_id"] = tenant_resp.get("id", tenant_resp.get("tenant_id", ""))
            result["success"] = True
        else:
            result["error"] = f"SSH key {key_id} not found in key listing"

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
