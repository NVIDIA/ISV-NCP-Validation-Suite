#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Reboot bare-metal instance and verify recovery - TEMPLATE (replace with your platform implementation).

This script is called during the "test" phase. It must:
  1. Verify the instance is running before reboot
  2. Issue a reboot command via your platform's API
  3. Wait for the instance to come back (bare-metal takes longer than VM:
     hardware POST, BIOS initialization, OS boot without hypervisor)
  4. Verify SSH connectivity is restored
  5. Check system uptime to confirm the reboot actually occurred
  6. Print a JSON object to stdout

Required JSON output fields:
  {
    "success": true,             # boolean - did the reboot + recovery succeed?
    "platform": "bm",            # string  - always "bm"
    "instance_id": "...",        # string  - instance identifier
    "instance_state": "running", # string  - must be "running" after reboot
    "public_ip": "54.x.x.x",     # string  - public IP (may change after reboot)
    "key_file": "/tmp/key.pem",  # string  - path to SSH private key
    "uptime_seconds": 45,        # int     - system uptime after reboot (should be low)
    "ssh_connectivity": true     # boolean - can we SSH after reboot?
  }

On failure, set "success": false and include an "error" field.

Usage:
    python reboot_instance.py --instance-id <id> --region <region> \
        --key-file /tmp/key.pem --public-ip 54.x.x.x

Reference implementation: ../aws/bm/reboot_instance.py
"""

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Reboot bare-metal instance (template)")
    parser.add_argument("--instance-id", required=True, help="Instance identifier")
    parser.add_argument("--region", required=True, help="Cloud region")
    parser.add_argument("--key-file", required=True, help="Path to SSH private key")
    parser.add_argument("--public-ip", required=True, help="Instance public IP")
    args = parser.parse_args()

    result: dict = {
        "success": False,
        "platform": "bm",
        "instance_id": args.instance_id,
        "instance_state": "",
        "public_ip": args.public_ip,
        "key_file": args.key_file,
        "uptime_seconds": None,
        "ssh_connectivity": False,
    }

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  TODO: Replace this block with your platform's reboot logic      ║
    # ║                                                                  ║
    # ║  Example (pseudocode):                                           ║
    # ║    client = MyCloudClient(region=args.region)                    ║
    # ║                                                                  ║
    # ║    1. Verify instance is running:                                ║
    # ║       info = client.describe_instance(args.instance_id)          ║
    # ║       assert info.state == "running"                             ║
    # ║                                                                  ║
    # ║    2. Issue reboot:                                              ║
    # ║       client.reboot_instance(args.instance_id)                   ║
    # ║                                                                  ║
    # ║    3. Wait for running (BM needs longer: hardware POST/BIOS):    ║
    # ║       time.sleep(120)  # initial wait for reboot to start        ║
    # ║       client.wait_until_running(args.instance_id, timeout=900)   ║
    # ║       info = client.describe_instance(args.instance_id)          ║
    # ║       result["instance_state"] = info.state                      ║
    # ║       result["public_ip"] = info.public_ip                       ║
    # ║                                                                  ║
    # ║    4. Verify SSH connectivity:                                   ║
    # ║       ssh_ok = wait_for_ssh(                                     ║
    # ║           host=result["public_ip"],                              ║
    # ║           key_file=args.key_file,                                ║
    # ║           max_attempts=60,                                       ║
    # ║           interval=15,                                           ║
    # ║       )                                                          ║
    # ║       result["ssh_connectivity"] = ssh_ok                        ║
    # ║                                                                  ║
    # ║    5. Check uptime (confirms reboot occurred):                   ║
    # ║       uptime = get_uptime_via_ssh(                               ║
    # ║           result["public_ip"], args.key_file                     ║
    # ║       )                                                          ║
    # ║       result["uptime_seconds"] = int(uptime)                     ║
    # ║       result["success"] = True                                   ║
    # ╚══════════════════════════════════════════════════════════════════╝

    result["error"] = "Not implemented - replace with your platform's instance reboot logic"
    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
