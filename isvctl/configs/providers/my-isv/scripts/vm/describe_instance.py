#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Describe VM instance - TEMPLATE (replace with your platform implementation).

This script is called during the "test" phase. It must:
  1. Query your platform for the current instance state
  2. Return network info (public IP) and pass through the SSH key file
  3. Print a JSON object to stdout

This is a lightweight step that validations bind to. SSH, GPU, and host-OS
checks run against this step's output, ensuring they execute in the test
phase (so teardown always runs, even if tests fail) AND prove the host
survived the full stop/start/reboot lifecycle.

Required JSON output fields:
  {
    "success": true,             # boolean - did the query succeed?
    "platform": "vm",            # string  - always "vm"
    "instance_id": "...",        # string  - instance identifier
    "state": "running",          # string  - current state
    "public_ip": "54.x.x.x",     # string  - public IP for SSH access
    "key_file": "/tmp/key.pem"   # string  - path to SSH private key
  }

On failure, set "success": false and include an "error" field.

Usage:
    python describe_instance.py --instance-id <id> --region <region> --key-file /tmp/key.pem

Reference implementation: ../aws/vm/describe_instance.py
"""

import argparse
import json
import os
import sys
from typing import Any

# ISVCTL_DEMO_MODE=1 enables demo-success output (used by `make demo-test`).
DEMO_MODE = os.environ.get("ISVCTL_DEMO_MODE") == "1"


def main() -> int:
    """Describe a VM instance (template)."""
    parser = argparse.ArgumentParser(description="Describe VM instance (template)")
    parser.add_argument("--instance-id", required=True, help="Instance identifier")
    parser.add_argument("--region", required=True, help="Cloud region")
    parser.add_argument("--key-file", required=True, help="Path to SSH private key")
    args = parser.parse_args()

    result: dict[str, Any] = {
        "success": False,
        "platform": "vm",
        "instance_id": args.instance_id,
        "state": "",
        "public_ip": "",
        "key_file": args.key_file,
    }

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  TODO: Replace this block with your platform's describe logic    ║
    # ║                                                                  ║
    # ║  Example (pseudocode):                                           ║
    # ║    client = MyCloudClient(region=args.region)                    ║
    # ║    info = client.describe_instance(args.instance_id)             ║
    # ║                                                                  ║
    # ║    result["state"] = info.state                # "running"       ║
    # ║    result["public_ip"] = info.public_ip        # for SSH         ║
    # ║    result["success"] = True                                      ║
    # ╚══════════════════════════════════════════════════════════════════╝

    if DEMO_MODE:
        result["state"] = "running"
        result["public_ip"] = "203.0.113.50"
        result["success"] = True
    else:
        result["error"] = "Not implemented - replace with your platform's instance describe logic"

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
