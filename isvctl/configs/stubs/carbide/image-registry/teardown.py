#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Delete all instances and OS resources created during image-registry testing.

Reads the state file to find all instance IDs and the OS ID, then
deletes them via ``carbidecli instance delete`` and
``carbidecli operating-system delete``.

Usage:
    python teardown.py --site-id <site-id>

Output JSON:
{
    "success": true,
    "platform": "image_registry",
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
    parser = argparse.ArgumentParser(description="Teardown Carbide image-registry resources")
    parser.add_argument("--region", default=os.environ.get("CARBIDE_REGION", ""))
    parser.add_argument("--site-id", default=os.environ.get("CARBIDE_SITE_ID", ""))
    args = parser.parse_args()

    state = load_state()
    resources_deleted: list[str] = []
    errors: list[str] = []

    result: dict[str, Any] = {
        "success": False,
        "platform": "image_registry",
        "resources_deleted": resources_deleted,
    }

    # Delete all tracked instances
    instance_ids = state.get("instance_ids", [])
    for instance_id in instance_ids:
        try:
            run_carbide("instance", "delete", "--id", instance_id)
            resources_deleted.append(f"instance:{instance_id}")
        except Exception as e:
            errors.append(f"instance:{instance_id}: {e}")

    # Delete the OS resource
    os_id = state.get("os_id", "")
    if os_id:
        try:
            run_carbide("operating-system", "delete", "--id", os_id)
            resources_deleted.append(f"operating-system:{os_id}")
        except Exception as e:
            errors.append(f"operating-system:{os_id}: {e}")

    if errors:
        result["errors"] = errors

    # Clear state
    save_state({})

    result["success"] = len(errors) == 0
    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
