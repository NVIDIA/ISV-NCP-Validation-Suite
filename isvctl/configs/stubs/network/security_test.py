#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Security blocking test - TEMPLATE (replace with your platform implementation).

This script is called during the "test" phase. It is SELF-CONTAINED:
  1. Create a temporary VPC
  2. Test that default security group denies all inbound traffic
  3. Add specific allow rules and verify they take effect
  4. Verify egress rules behave as expected
  5. Clean up all resources
  6. Print a JSON object to stdout

Required JSON output fields:
  {
    "success": true,                           # boolean - did all security tests pass?
    "platform": "network",                     # string  - always "network"
    "test_name": "security_blocking",          # string  - always "security_blocking"
    "tests": {                                 # object  - per-test results
      "default_deny": {
        "passed": true                         # boolean - default deny works?
      },
      "specific_allow": {
        "passed": true                         # boolean - allow rules work?
      },
      "egress_rules": {
        "passed": true                         # boolean - egress rules work?
      }
    }
  }

On failure, set "success": false and include an "error" field.

Usage:
    python security_test.py --region <region> --cidr 10.94.0.0/16

Reference implementation: ../aws/network/security_test.py
"""

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Security blocking test (template)")
    parser.add_argument("--region", required=True, help="Cloud region")
    parser.add_argument("--cidr", default="10.94.0.0/16", help="CIDR block for test VPC")
    args = parser.parse_args()  # noqa: F841 — used in TODO block below

    result: dict = {
        "success": False,
        "platform": "network",
        "test_name": "security_blocking",
        "tests": {
            "default_deny": {"passed": False},
            "specific_allow": {"passed": False},
            "egress_rules": {"passed": False},
        },
    }

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  TODO: Replace this block with your platform's security test     ║
    # ║                                                                  ║
    # ║  Example (pseudocode):                                           ║
    # ║    client = MyCloudClient(region=args.region)                    ║
    # ║    vpc = client.create_vpc(cidr=args.cidr)                       ║
    # ║    sg = client.create_security_group(vpc.id, "test-sg")          ║
    # ║                                                                  ║
    # ║    # Test default deny                                           ║
    # ║    rules = client.describe_sg_rules(sg.id)                       ║
    # ║    no_inbound = len(rules.inbound) == 0                          ║
    # ║    result["tests"]["default_deny"]["passed"] = no_inbound        ║
    # ║                                                                  ║
    # ║    # Test specific allow                                         ║
    # ║    client.authorize_ingress(sg.id, port=22, cidr="10.0.0.0/8")   ║
    # ║    rules = client.describe_sg_rules(sg.id)                       ║
    # ║    has_ssh = any(r.port == 22 for r in rules.inbound)            ║
    # ║    result["tests"]["specific_allow"]["passed"] = has_ssh         ║
    # ║                                                                  ║
    # ║    # Test egress rules                                           ║
    # ║    egress = client.describe_sg_rules(sg.id).outbound             ║
    # ║    result["tests"]["egress_rules"]["passed"] = len(egress) > 0   ║
    # ║                                                                  ║
    # ║    # Cleanup                                                     ║
    # ║    client.delete_vpc(vpc.id, cascade=True)                       ║
    # ║    result["success"] = True                                      ║
    # ╚══════════════════════════════════════════════════════════════════╝

    result["error"] = "Not implemented - replace with your platform's security test logic"
    print(json.dumps(result, indent=2))

    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
