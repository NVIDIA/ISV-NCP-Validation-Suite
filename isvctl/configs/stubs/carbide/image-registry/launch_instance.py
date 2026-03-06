#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Launch a Carbide instance using a previously created OS resource.

Uses ``carbidecli instance create`` with the OS ID from the upload step.
Maps to the image-registry template's ``launch_instance`` step.

Usage:
    python launch_instance.py --os-id <os-id> --site-id <site-id>

Output JSON:
{
    "success": true,
    "platform": "image_registry",
    "instance_id": "<id>",
    "public_ip": "...",
    "private_ip": "...",
    "state": "running",
    "key_path": ""
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


def wait_for_instance(instance_id: str, timeout: int = 300) -> dict[str, Any]:
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
    parser = argparse.ArgumentParser(description="Launch Carbide instance from OS image")
    parser.add_argument("--region", default=os.environ.get("CARBIDE_REGION", ""))
    parser.add_argument("--os-id", default=os.environ.get("CARBIDE_OS_ID", ""))
    parser.add_argument("--site-id", default=os.environ.get("CARBIDE_SITE_ID", ""))
    parser.add_argument("--name", default="ncp-img-test")
    args = parser.parse_args()

    if not args.os_id:
        # Fall back to state file
        state = load_state()
        args.os_id = state.get("os_id", "")

    if not args.os_id or not args.site_id:
        print(json.dumps({
            "success": False,
            "platform": "image_registry",
            "error": "os-id and site-id are required",
        }, indent=2))
        return 1

    instance_name = f"{args.name}-{int(time.time())}"

    result: dict[str, Any] = {
        "success": False,
        "platform": "image_registry",
    }

    try:
        resp = run_carbide(
            "instance", "create",
            "--name", instance_name,
            "--operating-system-id", args.os_id,
            "--site-id", args.site_id,
        )
        instance_id = resp.get("id", resp.get("instance_id", ""))
        result["instance_id"] = instance_id

        # Wait for instance to be running
        instance_data = wait_for_instance(instance_id)

        result["public_ip"] = instance_data.get("public_ip", instance_data.get("ip_address", ""))
        result["private_ip"] = instance_data.get("private_ip", instance_data.get("internal_ip", ""))
        result["state"] = "running"
        result["key_path"] = ""
        result["success"] = True

        # Persist for subsequent steps
        state = load_state()
        state["img_instance_id"] = instance_id
        state.setdefault("instance_ids", []).append(instance_id)
        save_state(state)

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
