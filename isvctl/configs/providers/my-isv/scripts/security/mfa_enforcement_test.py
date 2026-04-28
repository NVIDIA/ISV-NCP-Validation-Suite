#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""MFA enforcement test - TEMPLATE (replace with your platform implementation).

Verifies that ALL administrative interfaces (UI, CLI, API) are protected
by Multi-Factor Authentication.

Required JSON output fields:
  {
    "success": true,
    "platform": "security",
    "test_name": "mfa_enforcement",
    "interfaces_checked": 4,
    "tests": {
      "root_mfa_enabled":    {"passed": true},  # admin/root account has MFA
      "console_users_mfa":   {"passed": true},  # all console users have MFA
      "api_mfa_policy":      {"passed": true},  # API calls require MFA
      "cli_mfa_policy":      {"passed": true}   # CLI calls require MFA
    }
  }

Usage:
    python mfa_enforcement_test.py --region <region>
"""

import argparse
import json
import os
import sys
from typing import Any

DEMO_MODE = os.environ.get("ISVCTL_DEMO_MODE") == "1"


def main() -> int:
    """MFA enforcement test (template) and emit structured JSON result."""
    parser = argparse.ArgumentParser(description="MFA enforcement test (template)")
    parser.add_argument("--region", required=True, help="Cloud region")
    _args = parser.parse_args()

    result: dict[str, Any] = {
        "success": False,
        "platform": "security",
        "test_name": "mfa_enforcement",
        "interfaces_checked": 0,
        "tests": {
            "root_mfa_enabled": {"passed": False},
            "console_users_mfa": {"passed": False},
            "api_mfa_policy": {"passed": False},
            "cli_mfa_policy": {"passed": False},
        },
    }

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  TODO: Replace this block with your platform's MFA enforcement   ║
    # ║  test.                                                           ║
    # ║                                                                  ║
    # ║  Example checks:                                                 ║
    # ║    1. Verify root/admin account has MFA device attached          ║
    # ║    2. Verify all console-login users have MFA registered         ║
    # ║    3. Verify policies require MFA for sensitive API calls        ║
    # ║    4. Verify CLI sessions require MFA token                      ║
    # ╚══════════════════════════════════════════════════════════════════╝

    if DEMO_MODE:
        result["interfaces_checked"] = 4
        result["tests"] = {
            "root_mfa_enabled": {"passed": True, "message": "Root MFA enabled"},
            "console_users_mfa": {"passed": True, "message": "2/2 console users have MFA"},
            "api_mfa_policy": {"passed": True, "message": "MFA condition in API policy"},
            "cli_mfa_policy": {"passed": True, "message": "MFA condition in CLI policy"},
        }
        result["success"] = True
    else:
        result["error"] = "Not implemented - replace with your platform's MFA enforcement test"

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
