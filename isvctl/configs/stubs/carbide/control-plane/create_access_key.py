#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Create SSH key group and SSH key in Carbide.

Maps the template's "access key" concept to Carbide's SSH key model:
an SSH key group is created first, then an SSH key within it.

Usage:
    python create_access_key.py --username ncp-validation

Output JSON:
{
    "success": true,
    "platform": "control_plane",
    "username": "ncp-validation",
    "user_id": "<group-id>",
    "access_key_id": "<key-id>",
    "secret_access_key": "<public-key>"
}
"""

import argparse
import json
import os
import sys
import time
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common.carbide import load_state, run_carbide, save_state


def main() -> int:
    parser = argparse.ArgumentParser(description="Create Carbide SSH key group and key")
    parser.add_argument("--region", default=os.environ.get("CARBIDE_REGION", "us-west-2"))
    parser.add_argument("--username-prefix", default="ncp-validation")
    args = parser.parse_args()

    suffix = int(time.time())
    group_name = f"{args.username_prefix}-group-{suffix}"
    key_name = f"{args.username_prefix}-key-{suffix}"

    result: dict[str, Any] = {
        "success": False,
        "platform": "control_plane",
        "username": args.username_prefix,
    }

    existing_group_id = os.environ.get("CARBIDE_SSH_KEY_GROUP_ID", "")

    try:
        state = load_state()

        # SSH key group: reuse or create
        if existing_group_id:
            group_resp = run_carbide("ssh-key-group", "get", existing_group_id)
            group_id = group_resp.get("id", existing_group_id)
            group_name = group_resp.get("name", existing_group_id)
            state["ssh_key_group_created"] = False
        else:
            group_resp = run_carbide("ssh-key-group", "create", "--name", group_name)
            group_id = group_resp.get("id", group_resp.get("ssh_key_group_id", ""))
            state["ssh_key_group_created"] = True

        result["user_id"] = group_id

        # SSH key: always create (it's the test artifact)
        key_resp = run_carbide(
            "ssh-key", "create",
            "--name", key_name,
            "--ssh-key-group-id", group_id,
        )
        key_id = key_resp.get("id", key_resp.get("ssh_key_id", ""))
        public_key = key_resp.get("public_key", key_resp.get("key", ""))

        result["access_key_id"] = key_id
        result["secret_access_key"] = public_key
        result["success"] = True

        state["ssh_key_group_id"] = group_id
        state["ssh_key_group_name"] = group_name
        state["ssh_key_id"] = key_id
        state["ssh_key_name"] = key_name
        state["username"] = args.username_prefix
        save_state(state)

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
