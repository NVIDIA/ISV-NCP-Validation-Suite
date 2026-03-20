#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Floating IP test - TEMPLATE (replace with your platform implementation).

This script is called during the "test" phase. It is SELF-CONTAINED:
  1. Create a VPC and two instances
  2. Allocate a floating/elastic IP
  3. Associate it with instance A, verify
  4. Reassociate it to instance B, measure the switch time
  5. Verify the switch completed within the time limit (default: 10s)
  6. Clean up all resources
  7. Print a JSON object to stdout

Required JSON output fields:
  {
    "success": true,
    "platform": "network",
    "tests": {
      "allocate_eip": {"passed": true, "allocation_id": "...", "public_ip": "..."},
      "associate_to_a": {"passed": true},
      "verify_on_a": {"passed": true},
      "reassociate_to_b": {"passed": true, "switch_seconds": 2.3},
      "verify_on_b": {"passed": true},
      "verify_not_on_a": {"passed": true}
    }
  }

Usage:
    python floating_ip_test.py --region us-west-2 --cidr 10.92.0.0/16

Reference implementation: ../aws/network/floating_ip_test.py
"""

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Floating IP test (template)")
    parser.add_argument("--region", default="us-west-2", help="Cloud region")
    parser.add_argument("--cidr", default="10.92.0.0/16", help="CIDR for test VPC")
    parser.add_argument("--max-switch-seconds", type=int, default=10, help="Max switch time")
    args = parser.parse_args()  # noqa: F841

    result: dict = {
        "success": False,
        "platform": "network",
        "tests": {
            "allocate_eip": {"passed": False},
            "associate_to_a": {"passed": False},
            "verify_on_a": {"passed": False},
            "reassociate_to_b": {"passed": False},
            "verify_on_b": {"passed": False},
            "verify_not_on_a": {"passed": False},
        },
    }

    # TODO: Replace with your platform's floating IP implementation
    result["error"] = "Not implemented - replace with your platform's floating IP test logic"
    print(json.dumps(result, indent=2))

    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
