#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Create an OperatingSystem resource in Carbide (image upload equivalent).

Uses ``carbidecli operating-system create`` to register an OS with
iPXE/kickstart boot type. Maps to the image-registry template's
``upload_image`` step.

Usage:
    python upload_image.py --site-id <site-id>

Output JSON:
{
    "success": true,
    "platform": "image_registry",
    "image_id": "<os-id>",
    "image_name": "ncp-validation-os",
    "storage_bucket": "carbide",
    "disk_ids": ["<os-id>"]
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
    parser = argparse.ArgumentParser(description="Create Carbide OS resource")
    parser.add_argument("--region", default=os.environ.get("CARBIDE_REGION", ""))
    parser.add_argument("--site-id", default=os.environ.get("CARBIDE_SITE_ID", ""))
    parser.add_argument("--os-name", default="ncp-validation-os")
    args = parser.parse_args()

    if not args.site_id:
        print(json.dumps({
            "success": False,
            "platform": "image_registry",
            "error": "site-id is required (--site-id or CARBIDE_SITE_ID env var)",
        }, indent=2))
        return 1

    os_name = f"{args.os_name}-{int(time.time())}"

    result: dict[str, Any] = {
        "success": False,
        "platform": "image_registry",
        "image_name": os_name,
    }

    try:
        resp = run_carbide(
            "operating-system", "create",
            "--name", os_name,
            "--site-id", args.site_id,
            "--type", "ipxe",
        )
        os_id = resp.get("id", resp.get("operating_system_id", ""))

        result["image_id"] = os_id
        result["storage_bucket"] = "carbide"
        result["disk_ids"] = [os_id]
        result["success"] = True

        # Persist for subsequent steps
        state = load_state()
        state["os_id"] = os_id
        state["os_name"] = os_name
        state["site_id"] = args.site_id
        save_state(state)

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
