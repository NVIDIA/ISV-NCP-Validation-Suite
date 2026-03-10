#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Clean up temporary SSH key created during IAM validation.

Maps the IAM template's "teardown" step. Deletes the temporary SSH key
and key group created by create_user.py.

Usage:
    python delete_user.py

Output JSON:
{
    "success": true,
    "platform": "iam",
    "resources_deleted": ["ssh-key/<id>", "ssh-key-group/<id>"]
}
"""

import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common.carbide import load_state, run_carbide, save_state


def main() -> int:
    result: dict[str, Any] = {
        "success": False,
        "platform": "iam",
        "resources_deleted": [],
    }

    state = load_state()

    # Delete SSH key
    key_id = state.get("iam_ssh_key_id", "")
    if key_id:
        try:
            run_carbide("ssh-key", "delete", "--id", key_id)
            result["resources_deleted"].append(f"ssh-key/{key_id}")
        except RuntimeError as e:
            if "not found" not in str(e).lower():
                result["error"] = str(e)
                print(json.dumps(result, indent=2))
                return 1

    # Delete SSH key group
    group_id = state.get("iam_ssh_key_group_id", "")
    if group_id and state.get("iam_ssh_key_group_created", True):
        try:
            run_carbide("ssh-key-group", "delete", "--id", group_id)
            result["resources_deleted"].append(f"ssh-key-group/{group_id}")
        except RuntimeError as e:
            if "not found" not in str(e).lower():
                result["error"] = str(e)
                print(json.dumps(result, indent=2))
                return 1

    # Clean up state
    for key in ("iam_ssh_key_id", "iam_ssh_key_group_id", "iam_ssh_key_group_created"):
        state.pop(key, None)
    save_state(state)

    result["success"] = True
    result["message"] = "IAM test resources cleaned up"

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
