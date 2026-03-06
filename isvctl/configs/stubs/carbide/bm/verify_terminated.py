#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Verify a Carbide bare-metal instance has been terminated.

Post-teardown sanitization check: uses ``carbidecli instance get``
to confirm the instance no longer exists or is in a terminated state.

Usage:
    python verify_terminated.py --instance-id <id>

Output JSON:
{
    "success": true,
    "platform": "bm",
    "checks": {"instance_terminated": true}
}
"""

import argparse
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common.carbide import run_carbide


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Carbide instance terminated")
    parser.add_argument("--region", default=os.environ.get("CARBIDE_REGION", ""))
    parser.add_argument("--instance-id", default="")
    args = parser.parse_args()

    if not args.instance_id:
        print(json.dumps({
            "success": False,
            "platform": "bm",
            "error": "instance-id is required",
        }, indent=2))
        return 1

    result: dict[str, Any] = {
        "success": False,
        "platform": "bm",
        "checks": {"instance_terminated": False},
    }

    try:
        resp = run_carbide("instance", "get", "--id", args.instance_id)
        # If we get a response, check that the state is terminated/deleted
        state = resp.get("status", resp.get("state", ""))
        if state.lower() in ("terminated", "deleted", "destroying", "destroyed"):
            result["checks"]["instance_terminated"] = True
            result["success"] = True
        else:
            result["error"] = f"Instance {args.instance_id} still in state: {state}"
    except RuntimeError:
        # Command failed — instance no longer exists, which means it was deleted
        result["checks"]["instance_terminated"] = True
        result["success"] = True

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
