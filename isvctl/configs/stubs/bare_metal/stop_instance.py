#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Stop a bare-metal node and verify it reaches the powered-off state.

Template stub for ISV NCP Validation. Replace the TODO section with your
platform's API calls to power off a node without destroying it.

This script must:
  1. Power off the node via your platform's API (NOT delete/deprovision)
  2. Wait for the node to reach "stopped" state
  3. Confirm the node still exists (is not destroyed)

Required JSON output fields:
  success          (bool) - whether the operation succeeded
  platform         (str)  - always "bm"
  instance_id      (str)  - the stopped node ID
  state            (str)  - must be "stopped"
  stop_initiated   (bool) - whether the power-off API call succeeded
  error            (str, optional) - human-readable error message when success is false

Usage:
    python stop_instance.py --instance-id <id> --region <region>

Reference implementation (AWS):
    ../aws/bm/stop_instance.py
"""

import argparse
import json
import sys


def main() -> int:
    """Power off a bare-metal node and emit structured JSON result."""
    parser = argparse.ArgumentParser(description="Power off bare-metal node without destroying it")
    parser.add_argument("--instance-id", required=True, help="Node ID to power off")
    parser.add_argument("--region", required=True, help="Cloud region")
    args = parser.parse_args()

    result = {
        "success": False,
        "platform": "bm",
        "instance_id": args.instance_id,
        "state": "",
        "stop_initiated": False,
    }

    try:
        # ╔══════════════════════════════════════════════════════════════╗
        # ║  TODO: Replace this block with your platform's API calls     ║
        # ║                                                              ║
        # ║  1. Power off the node (do NOT delete/deprovision it)        ║
        # ║     power_off_node(args.instance_id, region=args.region)     ║
        # ║     result["stop_initiated"] = True                          ║
        # ║                                                              ║
        # ║  2. Wait for the node to reach "stopped" state               ║
        # ║     Note: BM may need longer timeouts than VMs               ║
        # ║     wait_for_powered_off(args.instance_id)                   ║
        # ║                                                              ║
        # ║  3. Populate result                                          ║
        # ║     result["state"] = "stopped"                              ║
        # ║     result["success"] = True                                 ║
        # ╚══════════════════════════════════════════════════════════════╝

        result["error"] = "Not implemented - replace with your platform's power-off logic"

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
