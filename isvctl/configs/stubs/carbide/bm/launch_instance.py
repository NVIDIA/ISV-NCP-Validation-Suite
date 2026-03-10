#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Launch a Carbide bare-metal GPU instance.

Uses ``carbidecli instance create`` to provision a bare-metal instance
with the specified OS and instance type. Waits for the instance to
reach running state.

Usage:
    python launch_instance.py --site-id <site-id> --os-id <os-id> --instance-type <type>

Output JSON:
{
    "success": true,
    "platform": "bm",
    "instance_id": "<id>",
    "public_ip": "...",
    "private_ip": "...",
    "state": "running",
    "ssh_user": "root",
    "key_file": "",
    "vpc_id": "<vpc-id>"
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


def wait_for_instance(instance_id: str, timeout: int = 600) -> dict[str, Any]:
    """Poll instance status until running or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = run_carbide("instance", "get", "--id", instance_id)
        state = resp.get("status", resp.get("state", ""))
        if state.lower() in ("running", "active"):
            return resp
        print(f"Instance {instance_id} state: {state}, waiting...", file=sys.stderr)
        time.sleep(15)
    raise RuntimeError(f"Instance {instance_id} did not reach running state within {timeout}s")


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch Carbide bare-metal instance")
    parser.add_argument("--region", default=os.environ.get("CARBIDE_REGION", ""))
    parser.add_argument("--site-id", default=os.environ.get("CARBIDE_SITE_ID", ""))
    parser.add_argument("--os-id", default=os.environ.get("CARBIDE_OS_ID", ""))
    parser.add_argument("--instance-type", default=os.environ.get("CARBIDE_INSTANCE_TYPE", ""))
    parser.add_argument("--name", default="ncp-bm-test-gpu")
    parser.add_argument("--instance-id", default=os.environ.get("CARBIDE_INSTANCE_ID", ""))
    parser.add_argument("--vpc-id", default=os.environ.get("CARBIDE_VPC_ID", ""))
    args = parser.parse_args()

    result: dict[str, Any] = {
        "success": False,
        "platform": "bm",
    }

    try:
        state = load_state()

        if args.instance_id:
            # Use pre-existing instance
            instance_data = run_carbide("instance", "get", "--id", args.instance_id)
            instance_id = instance_data.get("id", args.instance_id)
            state["instance_created"] = False
        else:
            # Create new instance
            if not args.site_id or not args.os_id or not args.instance_type:
                result["error"] = "site-id, os-id, and instance-type required when not using pre-existing instance"
                print(json.dumps(result, indent=2))
                return 1

            instance_name = f"{args.name}-{int(time.time())}"
            create_args = [
                "instance", "create",
                "--name", instance_name,
                "--operating-system-id", args.os_id,
                "--site-id", args.site_id,
                "--instance-type", args.instance_type,
            ]
            if args.vpc_id:
                create_args += ["--vpc-id", args.vpc_id]

            resp = run_carbide(*create_args)
            instance_id = resp.get("id", resp.get("instance_id", ""))
            state["instance_created"] = True

            # Wait for instance to be running
            instance_data = wait_for_instance(instance_id)

        result["instance_id"] = instance_id
        result["public_ip"] = instance_data.get("public_ip", instance_data.get("ip_address", ""))
        result["private_ip"] = instance_data.get("private_ip", instance_data.get("internal_ip", ""))
        result["state"] = "running"
        result["ssh_user"] = "root"
        result["key_file"] = ""
        result["vpc_id"] = instance_data.get("vpc_id", instance_data.get("network_id", ""))
        result["success"] = True

        state["instance_id"] = instance_id
        state["site_id"] = args.site_id
        save_state(state)

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
