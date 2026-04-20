#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Stable private IP test - TEMPLATE (replace with your platform implementation).

This script is called during the "test" phase. It is SELF-CONTAINED:
  1. Create a VPC and launch an instance
  2. Record its private IP address
  3. Stop the instance
  4. Start the instance again
  5. Verify the private IP is unchanged
  6. Clean up all resources
  7. Print a JSON object to stdout

Required JSON output fields:
  {
    "success": true,
    "platform": "network",
    "tests": {
      "create_instance": {"passed": true, "instance_id": "..."},
      "record_ip": {"passed": true, "private_ip": "..."},
      "stop_instance": {"passed": true},
      "start_instance": {"passed": true},
      "ip_unchanged": {"passed": true, "ip_before": "...", "ip_after": "..."}
    }
  }

Usage:
    python stable_ip_test.py --region <region> --cidr 10.91.0.0/16

Reference implementation: ../../aws/network/stable_ip_test.py
"""

import argparse
import json
import os
import sys

# ISVCTL_DEMO_MODE=1 enables demo-success output (used by `make demo-test`).
DEMO_MODE = os.environ.get("ISVCTL_DEMO_MODE") == "1"


def main() -> int:
    parser = argparse.ArgumentParser(description="Stable private IP test (template)")
    parser.add_argument("--region", required=True, help="Cloud region")
    parser.add_argument("--cidr", default="10.91.0.0/16", help="CIDR for test VPC")
    args = parser.parse_args()  # noqa: F841

    result: dict = {
        "success": False,
        "platform": "network",
        "tests": {
            "create_instance": {"passed": False},
            "record_ip": {"passed": False},
            "stop_instance": {"passed": False},
            "start_instance": {"passed": False},
            "ip_unchanged": {"passed": False},
        },
    }

    # TODO: Replace with your platform's stable IP implementation

    if DEMO_MODE:
        result["tests"] = {
            "create_instance": {"passed": True, "instance_id": "dummy-stable-instance"},
            "record_ip": {"passed": True, "private_ip": "10.91.0.10"},
            "stop_instance": {"passed": True},
            "start_instance": {"passed": True},
            "ip_unchanged": {"passed": True, "ip_before": "10.91.0.10", "ip_after": "10.91.0.10"},
        }
        result["success"] = True
    else:
        result["error"] = "Not implemented - replace with your platform's stable IP test logic"

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
