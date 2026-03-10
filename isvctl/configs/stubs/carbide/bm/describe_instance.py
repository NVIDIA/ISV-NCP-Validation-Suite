#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Describe a running Carbide bare-metal instance.

Lightweight test-phase step that fetches current instance state and
passes through SSH connection info. Validations (SSH, GPU, host OS)
bind to this step so they run in the test phase rather than setup.

Usage:
    python describe_instance.py --instance-id <id>

Output JSON:
{
    "success": true,
    "platform": "bm",
    "instance_id": "<id>",
    "public_ip": "...",
    "private_ip": "...",
    "state": "running",
    "ssh_user": "root",
    "key_file": ""
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
    parser = argparse.ArgumentParser(description="Describe Carbide bare-metal instance")
    parser.add_argument("--region", default=os.environ.get("CARBIDE_REGION", ""))
    parser.add_argument("--instance-id", default="")
    args = parser.parse_args()

    if not args.instance_id:
        state = load_state()
        args.instance_id = state.get("instance_id", "")

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
        "instance_id": args.instance_id,
    }

    try:
        resp = run_carbide("instance", "get", "--id", args.instance_id)

        status = resp.get("status", resp.get("state", ""))
        result["public_ip"] = resp.get("public_ip", resp.get("ip_address", ""))
        result["private_ip"] = resp.get("private_ip", resp.get("internal_ip", ""))
        result["state"] = "running" if status.lower() in ("running", "active") else status
        result["ssh_user"] = "root"
        result["key_file"] = ""
        result["success"] = result["state"] == "running"

        if not result["success"]:
            result["error"] = f"Instance {args.instance_id} is {result['state']}, expected running"

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
