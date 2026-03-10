#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Disable (delete) the SSH key in Carbide.

Carbide does not support disabling SSH keys, so this script deletes
the key instead.  The output uses the template's expected field names
(``status: Inactive``) for compatibility.

Usage:
    python disable_access_key.py --username ncp-validation --access-key-id <key-id>

Output JSON:
{
    "success": true,
    "platform": "control_plane",
    "access_key_id": "<key-id>",
    "status": "Inactive"
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
    parser = argparse.ArgumentParser(description="Disable (delete) Carbide SSH key")
    parser.add_argument("--username", default="")
    parser.add_argument("--access-key-id", default="")
    args = parser.parse_args()

    state = load_state()
    key_id = args.access_key_id or state.get("ssh_key_id", "")

    result: dict[str, Any] = {
        "success": False,
        "platform": "control_plane",
        "access_key_id": key_id,
    }

    try:
        run_carbide("ssh-key", "delete", "--id", key_id)
        result["status"] = "Inactive"
        result["success"] = True
    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
