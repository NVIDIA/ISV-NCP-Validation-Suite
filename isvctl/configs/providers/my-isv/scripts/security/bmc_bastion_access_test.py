#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""BMC bastion-access test - TEMPLATE (replace with your implementation).

Verifies that BMC/IPMI/Redfish management is reachable only through a
hardened bastion (jumphost), and that direct public/corporate-network
access is blocked.

Required JSON output fields:
  {
    "success": true,
    "platform": "security",
    "test_name": "bmc_bastion_access",
    "management_networks_checked": 1,
    "tests": {
      "bastion_identifiable": {"passed": true},
      "management_ingress_via_bastion_only": {"passed": true},
      "no_direct_public_route": {"passed": true},
      "bastion_hardened": {"passed": true}
    }
  }

Usage:
    python bmc_bastion_access_test.py --region <region>
"""

import argparse
import json
import os
import sys
from typing import Any

DEMO_MODE = os.environ.get("ISVCTL_DEMO_MODE") == "1"


def main() -> int:
    """Run the BMC bastion-access template and emit structured JSON."""
    parser = argparse.ArgumentParser(description="BMC bastion-access test (template)")
    parser.add_argument("--region", required=True, help="Cloud region")
    _args = parser.parse_args()

    result: dict[str, Any] = {
        "success": False,
        "platform": "security",
        "test_name": "bmc_bastion_access",
        "management_networks_checked": 0,
        "tests": {
            "bastion_identifiable": {"passed": False},
            "management_ingress_via_bastion_only": {"passed": False},
            "no_direct_public_route": {"passed": False},
            "bastion_hardened": {"passed": False},
        },
    }

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  TODO: Replace this block with your platform's SEC12-03 BMC      ║
    # ║  bastion-access validation.                                      ║
    # ║                                                                  ║
    # ║  Example (pseudocode):                                           ║
    # ║    bastion = lookup_bastion_host(region)                         ║
    # ║    assert bastion is not None                                    ║
    # ║    assert bmc_ingress_only_from(bastion)                         ║
    # ║    assert no_public_route_to_bmc_subnets()                       ║
    # ║    assert bastion_ssh_not_open_to_world()                        ║
    # ╚══════════════════════════════════════════════════════════════════╝

    if DEMO_MODE:
        result["management_networks_checked"] = 1
        result["tests"] = {
            "bastion_identifiable": {"passed": True},
            "management_ingress_via_bastion_only": {"passed": True},
            "no_direct_public_route": {"passed": True},
            "bastion_hardened": {"passed": True},
        }
        result["success"] = True
    else:
        result["error"] = "Not implemented - replace with your platform's BMC bastion-access test"

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
