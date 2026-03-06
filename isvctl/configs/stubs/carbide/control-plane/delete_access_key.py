#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Delete SSH key group in Carbide (teardown for access key lifecycle).

The SSH key itself was already deleted by ``disable_access_key``;
this step removes the parent SSH key group.

Usage:
    python delete_access_key.py --username ncp-validation --access-key-id <key-id>

Output JSON:
{
    "success": true,
    "platform": "control_plane",
    "resources_deleted": ["ssh-key-group/<id>"]
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
    parser = argparse.ArgumentParser(description="Delete Carbide SSH key group")
    parser.add_argument("--username", default="")
    parser.add_argument("--access-key-id", default="")
    parser.add_argument("--skip-destroy", action="store_true")
    args = parser.parse_args()

    result: dict[str, Any] = {"success": False, "platform": "control_plane"}

    if args.skip_destroy:
        result["success"] = True
        result["skipped"] = True
        print(json.dumps(result, indent=2))
        return 0

    state = load_state()
    group_id = state.get("ssh_key_group_id", "")

    try:
        run_carbide("ssh-key-group", "delete", "--id", group_id)
        result["resources_deleted"] = [f"ssh-key-group/{group_id}"]
        result["success"] = True
    except RuntimeError as e:
        # Already deleted is acceptable
        if "not found" in str(e).lower() or "404" in str(e):
            result["resources_deleted"] = [f"ssh-key-group/{group_id}"]
            result["success"] = True
            result["already_deleted"] = True
        else:
            result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
