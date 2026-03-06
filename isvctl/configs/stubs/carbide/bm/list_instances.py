#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""List Carbide instances and verify the target instance is present.

Uses ``carbidecli instance list`` to enumerate instances at the site,
then checks whether the target instance ID appears in the list.

Usage:
    python list_instances.py --site-id <site-id> --instance-id <id>

Output JSON:
{
    "success": true,
    "platform": "bm",
    "instances": [...],
    "count": N,
    "found_target": true,
    "target_instance": "<id>"
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
    parser = argparse.ArgumentParser(description="List Carbide instances")
    parser.add_argument("--region", default=os.environ.get("CARBIDE_REGION", ""))
    parser.add_argument("--site-id", default=os.environ.get("CARBIDE_SITE_ID", ""))
    parser.add_argument("--instance-id", default="")
    args = parser.parse_args()

    if not args.instance_id:
        state = load_state()
        args.instance_id = state.get("instance_id", "")

    result: dict[str, Any] = {
        "success": False,
        "platform": "bm",
        "instances": [],
        "count": 0,
        "found_target": False,
        "target_instance": args.instance_id,
    }

    try:
        list_args = ["instance", "list"]
        if args.site_id:
            list_args.extend(["--site-id", args.site_id])

        resp = run_carbide(*list_args)

        # Response may be a list directly or wrapped in a key
        instances = resp if isinstance(resp, list) else resp.get("instances", resp.get("items", []))
        result["instances"] = instances
        result["count"] = len(instances)

        # Check if target instance is in the list
        if args.instance_id:
            for inst in instances:
                inst_id = inst.get("id", inst.get("instance_id", ""))
                if inst_id == args.instance_id:
                    result["found_target"] = True
                    break

        result["success"] = True

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
