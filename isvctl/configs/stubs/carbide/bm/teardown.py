#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Delete a Carbide bare-metal instance.

Uses ``carbidecli instance delete`` to terminate the instance.

Usage:
    python teardown.py --instance-id <id>

Output JSON:
{
    "success": true,
    "platform": "bm",
    "resources_deleted": [...]
}
"""

import argparse
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common.carbide import load_state, run_carbide, save_state


def main() -> int:
    parser = argparse.ArgumentParser(description="Teardown Carbide bare-metal instance")
    parser.add_argument("--region", default=os.environ.get("CARBIDE_REGION", ""))
    parser.add_argument("--instance-id", default="")
    args = parser.parse_args()

    state = load_state()
    if not args.instance_id:
        args.instance_id = state.get("instance_id", "")

    result: dict[str, Any] = {
        "success": False,
        "platform": "bm",
        "resources_deleted": [],
    }

    if not args.instance_id:
        result["success"] = True
        result["message"] = "No instance to delete"
        print(json.dumps(result, indent=2))
        return 0

    if not state.get("instance_created", True):
        result["success"] = True
        result["skipped"] = True
        result["message"] = f"Instance {args.instance_id} is pre-existing, not deleting"
        print(json.dumps(result, indent=2))
        return 0

    try:
        run_carbide("instance", "delete", "--id", args.instance_id)
        result["resources_deleted"].append(f"instance:{args.instance_id}")
        result["success"] = True

        save_state({})

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
