#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Localized DNS test - TEMPLATE (replace with your platform implementation).

This script is called during the "test" phase. It is SELF-CONTAINED:
  1. Create a VPC with DNS support enabled
  2. Create a private DNS zone associated with the VPC
  3. Create a DNS A record pointing to a private endpoint
  4. Verify DNS settings are correct
  5. Verify the record resolves correctly
  6. Clean up all resources
  7. Print a JSON object to stdout

Required JSON output fields:
  {
    "success": true,
    "platform": "network",
    "tests": {
      "create_vpc_with_dns": {"passed": true, "vpc_id": "..."},
      "create_hosted_zone": {"passed": true, "zone_id": "..."},
      "create_dns_record": {"passed": true, "fqdn": "storage.internal.isv.test"},
      "verify_dns_settings": {"passed": true},
      "resolve_record": {"passed": true, "resolved_ip": "..."}
    }
  }

Usage:
    python dns_test.py --region <region> --cidr 10.89.0.0/16

Reference implementation: ../../aws/network/dns_test.py
"""

import argparse
import json
import os
import sys

# ISVCTL_DEMO_MODE=1 enables demo-success output (used by `make demo-test`).
DEMO_MODE = os.environ.get("ISVCTL_DEMO_MODE") == "1"


def main() -> int:
    parser = argparse.ArgumentParser(description="Localized DNS test (template)")
    parser.add_argument("--region", required=True, help="Cloud region")
    parser.add_argument("--cidr", default="10.89.0.0/16", help="CIDR for test VPC")
    parser.add_argument("--domain", default="internal.isv.test", help="Internal domain")
    args = parser.parse_args()

    result: dict = {
        "success": False,
        "platform": "network",
        "tests": {
            "create_vpc_with_dns": {"passed": False},
            "create_hosted_zone": {"passed": False},
            "create_dns_record": {"passed": False},
            "verify_dns_settings": {"passed": False},
            "resolve_record": {"passed": False},
        },
    }

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  TODO: Replace this block with your platform's DNS test          ║
    # ║                                                                  ║
    # ║  Example (pseudocode):                                           ║
    # ║    client = MyNetworkClient(region=args.region)                  ║
    # ║    vpc    = client.create_vpc(cidr=args.cidr, dns_support=True)  ║
    # ║    result["tests"]["create_vpc_with_dns"] = {"passed": True}     ║
    # ║    zone   = client.create_hosted_zone(args.domain, vpc.id)       ║
    # ║    result["tests"]["create_hosted_zone"] = {                     ║
    # ║        "passed": True, "zone_id": zone.id}                       ║
    # ║    fqdn   = f"web.{args.domain}"                                 ║
    # ║    client.create_dns_record(zone.id, fqdn, "10.89.0.10")         ║
    # ║    result["tests"]["create_dns_record"] = {                      ║
    # ║        "passed": True, "fqdn": fqdn}                             ║
    # ║    settings = client.get_vpc_dns_settings(vpc.id)                ║
    # ║    assert settings.dns_support and settings.dns_hostnames         ║
    # ║    result["tests"]["verify_dns_settings"] = {"passed": True}     ║
    # ║    resolved = client.resolve_dns(fqdn, vpc.id)                   ║
    # ║    result["tests"]["resolve_record"] = {                         ║
    # ║        "passed": True, "fqdn": fqdn,                             ║
    # ║        "resolved_ip": resolved.ip}                               ║
    # ║    result["success"] = True                                      ║
    # ╚══════════════════════════════════════════════════════════════════╝

    if DEMO_MODE:
        fqdn = f"web.{args.domain}"
        result["tests"] = {
            "create_vpc_with_dns": {"passed": True},
            "create_hosted_zone": {"passed": True, "zone_id": "dummy-zone"},
            "create_dns_record": {"passed": True, "fqdn": fqdn},
            "verify_dns_settings": {"passed": True},
            "resolve_record": {"passed": True, "fqdn": fqdn, "resolved_ip": "10.89.0.10"},
        }
        result["success"] = True
    else:
        result["error"] = "Not implemented - replace with your platform's localized DNS test logic"

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
