#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Start a stopped VM instance and verify it returns to running state.

Template stub for ISV NCP Validation. Replace the TODO section with your
platform's API calls to start a stopped instance and verify recovery.

This script must:
  1. Start the instance via your platform's API
  2. Wait for the instance to return to "running" state
  3. Verify SSH connectivity to the instance

Required JSON output fields:
  success          (bool) - whether the operation succeeded
  platform         (str)  - always "vm"
  instance_id      (str)  - the started instance ID
  state            (str)  - must be "running" after recovery
  public_ip        (str)  - public IP of the instance
  key_file         (str)  - path to SSH private key
  start_initiated  (bool) - whether the start API call succeeded
  ssh_ready        (bool) - whether SSH is reachable post-start
  error            (str, optional) - human-readable error message when success is false

Usage:
    python start_instance.py --instance-id <id> --region <region> \\
        --key-file /tmp/key.pem --public-ip <ip>

Reference implementation (AWS):
    ../aws/vm/start_instance.py
"""

import argparse
import json
import os
import sys

# ISVCTL_DEMO_MODE=1 enables demo-success output (used by `make demo-test`).
DEMO_MODE = os.environ.get("ISVCTL_DEMO_MODE") == "1"


def main() -> int:
    parser = argparse.ArgumentParser(description="Start stopped VM instance and verify recovery")
    parser.add_argument("--instance-id", required=True, help="Instance ID to start")
    parser.add_argument("--region", required=True, help="Cloud region")
    parser.add_argument("--key-file", required=True, help="Path to SSH private key")
    parser.add_argument("--public-ip", required=True, help="Instance public IP address")
    args = parser.parse_args()

    result = {
        "success": False,
        "platform": "vm",
        "instance_id": args.instance_id,
        "state": "",
        "public_ip": args.public_ip,
        "key_file": args.key_file,
        "start_initiated": False,
        "ssh_ready": False,
    }

    try:
        # ╔══════════════════════════════════════════════════════════════╗
        # ║  TODO: Replace this block with your platform's API calls     ║
        # ║                                                              ║
        # ║  1. Start the instance via your platform's API               ║
        # ║     start_instance(args.instance_id, region=args.region)     ║
        # ║     result["start_initiated"] = True                         ║
        # ║                                                              ║
        # ║  2. Wait for the instance to return to "running" state       ║
        # ║     wait_for_running(args.instance_id)                       ║
        # ║                                                              ║
        # ║  3. Verify SSH connectivity                                  ║
        # ║     ssh_ok = wait_for_ssh(                                   ║
        # ║         host=args.public_ip,                                 ║
        # ║         key_file=args.key_file,                              ║
        # ║     )                                                        ║
        # ║     result["ssh_ready"] = ssh_ok                             ║
        # ║                                                              ║
        # ║  4. Populate result                                          ║
        # ║     result["state"] = "running"                              ║
        # ║     result["success"] = True                                 ║
        # ╚══════════════════════════════════════════════════════════════╝

        if DEMO_MODE:
            result["instance_id"] = args.instance_id
            result["state"] = "running"
            result["public_ip"] = args.public_ip
            result["key_file"] = args.key_file
            result["start_initiated"] = True
            result["ssh_ready"] = True
            result["success"] = True
        else:
            result["error"] = "Not implemented - replace with your platform's start logic"

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
