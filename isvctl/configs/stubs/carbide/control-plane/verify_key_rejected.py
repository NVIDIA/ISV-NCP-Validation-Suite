#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Verify the deleted SSH key no longer appears in Carbide.

Carbide does not have a "reject" concept; instead we verify
that the previously deleted SSH key is absent from the key listing.

Usage:
    python verify_key_rejected.py --access-key-id <key-id>

Output JSON:
{
    "success": true,
    "platform": "control_plane",
    "rejected": true,
    "error_code": "KeyNotFound"
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
    parser = argparse.ArgumentParser(description="Verify Carbide SSH key is gone")
    parser.add_argument("--access-key-id", default="")
    parser.add_argument("--secret-access-key", default="")
    parser.add_argument("--region", default=os.environ.get("CARBIDE_REGION", "us-west-2"))
    parser.add_argument("--wait", type=int, default=0, help="Seconds to wait (unused)")
    parser.add_argument("--retries", type=int, default=3, help="Number of retry attempts")
    args = parser.parse_args()

    state = load_state()
    key_id = args.access_key_id or state.get("ssh_key_id", "")

    result: dict[str, Any] = {
        "success": False,
        "platform": "control_plane",
        "rejected": False,
    }

    try:
        keys_resp = run_carbide("ssh-key", "list")
        keys = keys_resp if isinstance(keys_resp, list) else keys_resp.get("items", [])

        found = any(
            k.get("id", k.get("ssh_key_id", "")) == key_id
            for k in keys
        )

        if not found:
            result["rejected"] = True
            result["error_code"] = "KeyNotFound"
            result["success"] = True
        else:
            result["error"] = f"SSH key {key_id} still present after deletion"

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    # Always exit 0 - let validation check the 'rejected' field
    return 0


if __name__ == "__main__":
    sys.exit(main())
