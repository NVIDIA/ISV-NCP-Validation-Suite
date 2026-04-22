#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Service account long-lived credential test - TEMPLATE.

Verifies that out-of-cluster service accounts can authenticate using
long-lived credentials (API keys, service account keys, etc.).  This
covers the SEC03-01 requirement.

Required JSON output fields:
  {
    "success": true,
    "platform": "security",
    "test_name": "sa_credential_test",
    "authenticated": true,
    "credential_type": "api_key",
    "identity": "sa-validation-test@project.iam",
    "expires_at": null
  }

Usage:
    python sa_credential_test.py --region <region>
"""

import argparse
import json
import os
import sys
from typing import Any

DEMO_MODE = os.environ.get("ISVCTL_DEMO_MODE") == "1"


def main() -> int:
    """SA credential test (template) and emit structured JSON result."""
    parser = argparse.ArgumentParser(
        description="Service account credential test (template)"
    )
    parser.add_argument("--region", required=True, help="Cloud region")
    _args = parser.parse_args()

    result: dict[str, Any] = {
        "success": False,
        "platform": "security",
        "test_name": "sa_credential_test",
        "authenticated": False,
        "credential_type": "",
        "identity": "",
        "expires_at": None,
    }

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  TODO: Replace this block with your platform's SA credential     ║
    # ║  test.                                                           ║
    # ║                                                                  ║
    # ║  Example (pseudocode):                                           ║
    # ║    sa = create_service_account("validation-test")                ║
    # ║    key = create_long_lived_key(sa)                               ║
    # ║    identity = authenticate_with_key(key)                         ║
    # ║    result["authenticated"] = identity is not None                ║
    # ║    result["credential_type"] = "service_account_key"             ║
    # ║    result["identity"] = identity.principal                       ║
    # ╚══════════════════════════════════════════════════════════════════╝

    if DEMO_MODE:
        result["authenticated"] = True
        result["credential_type"] = "api_key"
        result["identity"] = "sa-validation-test@my-isv.iam"
        result["expires_at"] = None
        result["success"] = True
    else:
        result["error"] = (
            "Not implemented - replace with your platform's service account credential test"
        )

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
