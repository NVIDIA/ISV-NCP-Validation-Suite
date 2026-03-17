#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Traffic flow test - TEMPLATE (replace with your platform implementation).

This script is called during the "test" phase. It is SELF-CONTAINED:
  1. Create a temporary VPC with subnets and security groups
  2. Launch instances in different subnets
  3. Test that ping is ALLOWED between instances in the same security group
  4. Test that ping is BLOCKED when security group rules deny ICMP
  5. Test internet access (e.g., via NAT gateway or internet gateway)
  6. Clean up all resources
  7. Print a JSON object to stdout

Required JSON output fields:
  {
    "success": true,                           # boolean - did all traffic tests pass?
    "platform": "network",                     # string  - always "network"
    "test_name": "traffic_flow",               # string  - always "traffic_flow"
    "tests": {                                 # object  - per-test results
      "ping_allowed": {
        "passed": true                         # boolean - ping works when allowed?
      },
      "ping_blocked": {
        "passed": true                         # boolean - ping blocked when denied?
      },
      "internet_access": {
        "passed": true                         # boolean - outbound internet works?
      }
    }
  }

On failure, set "success": false and include an "error" field.

Usage:
    python traffic_test.py --region us-west-2 --cidr 10.93.0.0/16

Reference implementation: ../../../stubs/aws/network/traffic_test.py
"""

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Traffic flow test (template)")
    parser.add_argument("--region", default="us-west-2", help="Cloud region")
    parser.add_argument("--cidr", default="10.93.0.0/16", help="CIDR block for test VPC")
    args = parser.parse_args()  # noqa: F841 — used in TODO block below

    result: dict = {
        "success": False,
        "platform": "network",
        "test_name": "traffic_flow",
        "tests": {
            "ping_allowed": {"passed": False},
            "ping_blocked": {"passed": False},
            "internet_access": {"passed": False},
        },
    }

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  TODO: Replace this block with your platform's traffic test      ║
    # ║                                                                  ║
    # ║  Example (pseudocode):                                           ║
    # ║    client = MyCloudClient(region=args.region)                    ║
    # ║    vpc = client.create_vpc(cidr=args.cidr)                       ║
    # ║    subnet = client.create_subnet(vpc.id, "10.93.1.0/24")         ║
    # ║    sg = client.create_security_group(vpc.id, "traffic-test")     ║
    # ║    client.authorize_ingress(sg.id, protocol="icmp", cidr="*")    ║
    # ║                                                                  ║
    # ║    inst_a = client.launch_instance(subnet.id, sg.id)             ║
    # ║    inst_b = client.launch_instance(subnet.id, sg.id)             ║
    # ║                                                                  ║
    # ║    # Test ping allowed                                           ║
    # ║    ok = client.ping(inst_a.id, inst_b.private_ip)                ║
    # ║    result["tests"]["ping_allowed"]["passed"] = ok                ║
    # ║                                                                  ║
    # ║    # Test ping blocked (revoke ICMP rule)                        ║
    # ║    client.revoke_ingress(sg.id, protocol="icmp")                 ║
    # ║    blocked = not client.ping(inst_a.id, inst_b.private_ip)       ║
    # ║    result["tests"]["ping_blocked"]["passed"] = blocked           ║
    # ║                                                                  ║
    # ║    # Test internet access                                        ║
    # ║    igw = client.create_internet_gateway(vpc.id)                  ║
    # ║    inet = client.ping(inst_a.id, "8.8.8.8")                      ║
    # ║    result["tests"]["internet_access"]["passed"] = inet           ║
    # ║                                                                  ║
    # ║    # Cleanup                                                     ║
    # ║    client.terminate_instances([inst_a.id, inst_b.id])            ║
    # ║    client.delete_vpc(vpc.id, cascade=True)                       ║
    # ║    result["success"] = True                                      ║
    # ╚══════════════════════════════════════════════════════════════════╝

    result["error"] = "Not implemented - replace with your platform's traffic test logic"
    print(json.dumps(result, indent=2))

    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
