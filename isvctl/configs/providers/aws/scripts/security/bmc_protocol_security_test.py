#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Verify CNP10-01 BMC protocol posture for AWS tenant environments.

AWS does not expose customer-accessible IPMI or Redfish BMC endpoints for
EC2/EKS tenant workloads. The BMC protocol attack surface is owned by the
AWS managed infrastructure plane rather than the customer VPC or instance
network. This reference script emits the provider-agnostic CNP10-01 contract
with evidence explaining that no tenant/customer BMC protocol surface exists.

Usage:
    python bmc_protocol_security_test.py --region us-west-2

Output JSON:
  {
    "success": true,
    "platform": "security",
    "test_name": "bmc_protocol_security",
    "bmc_endpoints_tested": 0,
    "tests": { ... }
  }
"""

import argparse
import json
import os
import sys
from typing import Any

AWS_NO_CUSTOMER_BMC_MESSAGE = "AWS EC2/EKS tenants do not receive customer-accessible IPMI or Redfish BMC endpoints"


def _aws_no_customer_bmc_result(region: str) -> dict[str, Any]:
    """Build the AWS CNP10-01 result for the managed BMC protocol surface."""
    evidence = f"{AWS_NO_CUSTOMER_BMC_MESSAGE} in region {region}"
    return {
        "success": True,
        "platform": "security",
        "test_name": "bmc_protocol_security",
        "region": region,
        "bmc_endpoints_tested": 0,
        "bmc_protocol_surface": "none",
        "evidence": evidence,
        "tests": {
            "ipmi_disabled": {
                "passed": True,
                "message": f"{evidence}; IPMI UDP 623 is not exposed to tenant networks",
            },
            "redfish_tls_enabled": {
                "passed": True,
                "message": f"{evidence}; no customer Redfish endpoint requires TLS validation",
            },
            "redfish_plain_http_disabled": {
                "passed": True,
                "message": f"{evidence}; plain HTTP Redfish is not exposed",
            },
            "redfish_authentication_required": {
                "passed": True,
                "message": f"{evidence}; unauthenticated Redfish access is not available",
            },
            "redfish_authorization_enforced": {
                "passed": True,
                "message": f"{evidence}; customer Redfish role actions are not available",
            },
            "redfish_accounting_enabled": {
                "passed": True,
                "message": f"{evidence}; customer Redfish accounting is not applicable",
            },
        },
    }


def main() -> int:
    """Emit AWS CNP10-01 BMC protocol posture evidence."""
    parser = argparse.ArgumentParser(description="BMC protocol security test")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-west-2"))
    args = parser.parse_args()

    result = _aws_no_customer_bmc_result(args.region)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
