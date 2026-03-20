#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Serial console access test - TEMPLATE (replace with your platform implementation).

This script retrieves serial console output from a running instance.
Read-only access is sufficient; interactive access is preferred but not required.

Required JSON output fields:
  {
    "success": true,
    "platform": "vm",
    "instance_id": "<id>",
    "console_available": true,
    "serial_access_enabled": true,
    "output_length": 4096,
    "output_snippet": "... last 500 chars ..."
  }

Usage:
    python serial_console.py --instance-id <id> --region us-west-2

Reference implementation: ../aws/vm/serial_console.py
"""

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Serial console access test (template)")
    parser.add_argument("--instance-id", required=True, help="Instance ID")
    parser.add_argument("--region", default="us-west-2", help="Cloud region")
    args = parser.parse_args()

    result: dict = {
        "success": False,
        "platform": "vm",
        "instance_id": args.instance_id,
        "console_available": False,
        "serial_access_enabled": False,
    }

    # TODO: Replace with your platform's serial console implementation
    result["error"] = "Not implemented - replace with your platform's serial console logic"
    print(json.dumps(result, indent=2))

    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
