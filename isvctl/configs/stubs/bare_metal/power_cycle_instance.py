#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Power-cycle a bare-metal node (hard power off + power on) - TEMPLATE.

This script is called during the "test" phase. It must:
  1. Verify the instance is running before the power-cycle
  2. Issue a hard power-off via your platform's API (NOT an OS-level reboot)
  3. Confirm the node reached powered-off state
  4. Issue a power-on command
  5. Wait for the node to come back (bare-metal takes longer: hardware POST,
     BIOS initialization, OS boot without hypervisor)
  6. Verify SSH connectivity is restored
  7. Print a JSON object to stdout

Power-cycle vs reboot:
  - Reboot (step 8) is an OS-level restart; the hardware stays powered.
  - Power-cycle is a full hardware reset: power off → power on. This validates
    that the node recovers from complete power loss, exercising firmware
    initialization, BIOS POST, and a cold OS boot.

Required JSON output fields:
  {
    "success": true,                # boolean - did the full cycle succeed?
    "platform": "bm",              # string  - always "bm"
    "instance_id": "...",           # string  - instance identifier
    "state": "running",             # string  - must be "running" after recovery
    "public_ip": "54.x.x.x",      # string  - public IP (may change after cycle)
    "key_file": "/tmp/key.pem",    # string  - path to SSH private key
    "power_cycle_initiated": true,  # boolean - was the power-off API call made?
    "power_was_off": true,          # boolean - did the node actually power off?
    "ssh_ready": true,              # boolean - can we SSH after recovery?
    "recovery_seconds": 180         # int     - seconds from power-on to SSH ready
  }

On failure, set "success": false and include an "error" field.

Usage:
    python power_cycle_instance.py --instance-id <id> --region <region> \
        --key-file /tmp/key.pem --public-ip 54.x.x.x
"""

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Power-cycle bare-metal node (template)")
    parser.add_argument("--instance-id", required=True, help="Instance identifier")
    parser.add_argument("--region", default="us-west-2", help="Cloud region")
    parser.add_argument("--key-file", required=True, help="Path to SSH private key")
    parser.add_argument("--public-ip", required=True, help="Instance public IP")
    args = parser.parse_args()

    result: dict = {
        "success": False,
        "platform": "bm",
        "instance_id": args.instance_id,
        "state": "",
        "public_ip": args.public_ip,
        "key_file": args.key_file,
        "power_cycle_initiated": False,
        "power_was_off": False,
        "ssh_ready": False,
        "recovery_seconds": None,
    }

    try:
        # ╔══════════════════════════════════════════════════════════════════╗
        # ║  TODO: Replace this block with your platform's power-cycle logic ║
        # ║                                                                  ║
        # ║  Example (pseudocode):                                           ║
        # ║    client = MyCloudClient(region=args.region)                    ║
        # ║                                                                  ║
        # ║    1. Verify instance is running:                                ║
        # ║       info = client.describe_instance(args.instance_id)          ║
        # ║       assert info.state == "running"                             ║
        # ║                                                                  ║
        # ║    2. Power off (hard stop, not OS-level shutdown):              ║
        # ║       client.stop_instance(args.instance_id, force=True)         ║
        # ║       result["power_cycle_initiated"] = True                     ║
        # ║                                                                  ║
        # ║    3. Wait for powered-off state:                                ║
        # ║       client.wait_until_stopped(args.instance_id, timeout=600)   ║
        # ║       result["power_was_off"] = True                             ║
        # ║                                                                  ║
        # ║    4. Power on:                                                  ║
        # ║       start_time = time.time()                                   ║
        # ║       client.start_instance(args.instance_id)                    ║
        # ║       client.wait_until_running(args.instance_id, timeout=900)   ║
        # ║       info = client.describe_instance(args.instance_id)          ║
        # ║       result["state"] = info.state                               ║
        # ║       result["public_ip"] = info.public_ip                       ║
        # ║                                                                  ║
        # ║    5. Verify SSH connectivity:                                   ║
        # ║       ssh_ok = wait_for_ssh(                                     ║
        # ║           host=result["public_ip"],                              ║
        # ║           key_file=args.key_file,                                ║
        # ║           max_attempts=60,                                       ║
        # ║           interval=15,                                           ║
        # ║       )                                                          ║
        # ║       result["ssh_ready"] = ssh_ok                               ║
        # ║       result["recovery_seconds"] = int(time.time() - start_time) ║
        # ║       result["success"] = True                                   ║
        # ╚══════════════════════════════════════════════════════════════════╝

        result["error"] = "Not implemented - replace with your platform's power-cycle logic"

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
