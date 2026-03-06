#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""OS install config CRUD lifecycle via Carbide operating-system API.

Exercises get, list, update, and delete on the OperatingSystem resource
to validate full CRUD capability. Maps to the image-registry template's
``crud_install_config`` step.

Usage:
    python crud_install_config.py --os-id <os-id> --site-id <site-id>

Output JSON:
{
    "success": true,
    "platform": "image_registry",
    "config_id": "<os-id>",
    "config_name": "ncp-test-config",
    "operations": {"create": true, "read": true, "update": true, "delete": true}
}
"""

import argparse
import json
import os
import sys
import time
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common.carbide import load_state, run_carbide


def main() -> int:
    parser = argparse.ArgumentParser(description="Carbide OS install config CRUD lifecycle")
    parser.add_argument("--region", default=os.environ.get("CARBIDE_REGION", ""))
    parser.add_argument("--os-id", default=os.environ.get("CARBIDE_OS_ID", ""))
    parser.add_argument("--site-id", default=os.environ.get("CARBIDE_SITE_ID", ""))
    args = parser.parse_args()

    if not args.os_id:
        state = load_state()
        args.os_id = state.get("os_id", "")

    if not args.os_id:
        print(json.dumps({
            "success": False,
            "platform": "image_registry",
            "error": "os-id is required (--os-id or from previous step state)",
        }, indent=2))
        return 1

    config_name = f"ncp-test-config-{int(time.time())}"

    result: dict[str, Any] = {
        "success": False,
        "platform": "image_registry",
        "config_id": args.os_id,
        "config_name": config_name,
        "operations": {"create": False, "read": False, "update": False, "delete": False},
    }

    try:
        # CREATE: A new OS config for CRUD testing
        create_resp = run_carbide(
            "operating-system", "create",
            "--name", config_name,
            "--site-id", args.site_id,
            "--type", "ipxe",
        )
        crud_os_id = create_resp.get("id", create_resp.get("operating_system_id", ""))
        result["config_id"] = crud_os_id
        result["operations"]["create"] = True

        # READ: Get the OS config
        run_carbide("operating-system", "get", "--id", crud_os_id)
        result["operations"]["read"] = True

        # UPDATE: Update the OS config description
        run_carbide(
            "operating-system", "update",
            "--id", crud_os_id,
            "--name", f"{config_name}-updated",
        )
        result["operations"]["update"] = True

        # DELETE: Remove the CRUD test config
        run_carbide("operating-system", "delete", "--id", crud_os_id)
        result["operations"]["delete"] = True

        result["success"] = all(result["operations"].values())

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
