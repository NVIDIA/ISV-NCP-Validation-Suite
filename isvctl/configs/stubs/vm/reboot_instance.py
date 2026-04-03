#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Reboot a VM instance and validate it comes back healthy.

Template stub for ISV NCP Validation. Replace the TODO section with your
platform's API calls to reboot an instance and verify recovery.

This script must:
  1. Initiate a reboot via your platform's API
  2. Wait for the instance to return to "running" state
  3. Verify SSH connectivity to the instance
  4. Capture system uptime to confirm the reboot occurred

Required JSON output fields:
  success           (bool)  - whether the operation succeeded
  platform          (str)   - always "vm"
  instance_id       (str)   - the rebooted instance ID
  instance_state    (str)   - must be "running" after recovery
  public_ip         (str)   - public IP of the instance
  key_file          (str)   - path to SSH private key
  uptime_seconds    (int)   - system uptime after reboot (proves reboot happened)
  ssh_connectivity  (bool)  - whether SSH is reachable post-reboot
  error             (str, optional) - human-readable error message provided when success is false

Usage:
    python reboot_instance.py --instance-id i-xxx --region <region> \\
        --key-file /tmp/key.pem --public-ip 54.x.x.x

Reference implementation (AWS):
    ../aws/vm/reboot_instance.py
"""

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Reboot VM instance and verify recovery")
    parser.add_argument("--instance-id", required=True, help="Instance ID to reboot")
    parser.add_argument("--region", required=True, help="Cloud region")
    parser.add_argument("--key-file", required=True, help="Path to SSH private key")
    parser.add_argument("--public-ip", required=True, help="Instance public IP address")
    args = parser.parse_args()

    result = {
        "success": False,
        "platform": "vm",
        "instance_id": args.instance_id,
        "instance_state": "",
        "public_ip": args.public_ip,
        "key_file": args.key_file,
        "uptime_seconds": None,
        "ssh_connectivity": False,
    }

    try:
        # ╔══════════════════════════════════════════════════════════════╗
        # ║  TODO: Replace this block with your platform's API calls     ║
        # ║                                                              ║
        # ║  1. Reboot the instance via your platform's API              ║
        # ║     reboot_instance(args.instance_id, region=args.region)    ║
        # ║                                                              ║
        # ║  2. Wait for the instance to return to "running" state       ║
        # ║     wait_for_running(args.instance_id)                       ║
        # ║                                                              ║
        # ║  3. Verify SSH connectivity                                  ║
        # ║     ssh_ok = wait_for_ssh(                                   ║
        # ║         host=args.public_ip,                                 ║
        # ║         key_file=args.key_file,                              ║
        # ║     )                                                        ║
        # ║     result["ssh_connectivity"] = ssh_ok                      ║
        # ║                                                              ║
        # ║  4. Get uptime to confirm reboot (should be low)             ║
        # ║     uptime = ssh_command(args.public_ip, args.key_file,      ║
        # ║         "cat /proc/uptime | cut -d' ' -f1")                  ║
        # ║     result["uptime_seconds"] = int(float(uptime))            ║
        # ║                                                              ║
        # ║  5. Populate result                                          ║
        # ║     result["instance_state"] = "running"                     ║
        # ║     result["success"] = True                                 ║
        # ╚══════════════════════════════════════════════════════════════╝

        result["error"] = "Not implemented - replace with your platform's reboot logic"

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
