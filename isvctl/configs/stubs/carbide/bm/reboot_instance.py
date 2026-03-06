#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Reboot a Carbide bare-metal instance and wait for it to come back.

Uses ``carbidecli instance reboot`` then polls until the instance
returns to running state and SSH is reachable.

Usage:
    python reboot_instance.py --instance-id <id> --public-ip <ip>

Output JSON:
{
    "success": true,
    "platform": "bm",
    "instance_id": "<id>",
    "reboot_initiated": true,
    "state": "running",
    "ssh_ready": true,
    "uptime_seconds": 120
}
"""

import argparse
import json
import os
import socket
import sys
import time
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common.carbide import load_state, run_carbide


def check_ssh(host: str, port: int = 22, timeout: int = 5) -> bool:
    """Check if SSH port is reachable."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


def wait_for_ready(instance_id: str, public_ip: str, timeout: int = 600) -> dict[str, Any]:
    """Wait for instance to be running and SSH-reachable after reboot."""
    deadline = time.monotonic() + timeout
    reboot_time = time.monotonic()

    # Wait for instance to return to running state
    while time.monotonic() < deadline:
        try:
            resp = run_carbide("instance", "get", "--id", instance_id)
            state = resp.get("status", resp.get("state", ""))
            if state.lower() in ("running", "active"):
                break
        except Exception:
            pass
        time.sleep(10)

    # Wait for SSH to be reachable
    ssh_ready = False
    while time.monotonic() < deadline:
        if check_ssh(public_ip):
            ssh_ready = True
            break
        time.sleep(10)

    uptime = int(time.monotonic() - reboot_time)
    return {"ssh_ready": ssh_ready, "uptime_seconds": uptime}


def main() -> int:
    parser = argparse.ArgumentParser(description="Reboot Carbide bare-metal instance")
    parser.add_argument("--region", default=os.environ.get("CARBIDE_REGION", ""))
    parser.add_argument("--instance-id", default="")
    parser.add_argument("--public-ip", default="")
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
        "reboot_initiated": False,
    }

    try:
        run_carbide("instance", "reboot", "--id", args.instance_id)
        result["reboot_initiated"] = True

        if args.public_ip:
            ready = wait_for_ready(args.instance_id, args.public_ip)
            result["ssh_ready"] = ready["ssh_ready"]
            result["uptime_seconds"] = ready["uptime_seconds"]
        else:
            result["ssh_ready"] = False
            result["uptime_seconds"] = 0

        result["state"] = "running"
        result["success"] = True

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
