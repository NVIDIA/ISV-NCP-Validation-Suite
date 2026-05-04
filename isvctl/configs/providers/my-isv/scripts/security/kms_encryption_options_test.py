#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""KMS encryption options test - TEMPLATE.

Verifies that the platform supports both provider-managed and
customer-managed encryption keys for control-plane encryption.

Usage:
    python kms_encryption_options_test.py --region <region>
"""

import argparse
import json
import os
import sys
from typing import Any

DEMO_MODE = os.environ.get("ISVCTL_DEMO_MODE") == "1"


def main() -> int:
    """KMS encryption options test (template) and emit structured JSON result."""
    parser = argparse.ArgumentParser(description="KMS encryption options test (template)")
    parser.add_argument("--region", required=True, help="Cloud region")
    _args = parser.parse_args()

    result: dict[str, Any] = {
        "success": False,
        "platform": "security",
        "test_name": "kms_encryption_options_test",
        "provider_managed_key_id": "",
        "customer_managed_key_id": "",
        "tests": {
            "provider_managed_key_available": {"passed": False},
            "customer_managed_key_available": {"passed": False},
            "both_options_supported": {"passed": False},
        },
    }

    # TODO: Replace this block with your platform's KMS option checks. Prove
    # that tenants can choose both provider-managed keys and customer-managed
    # keys, and include non-empty identifiers for both options.

    if DEMO_MODE:
        result["provider_managed_key_id"] = "my-isv-provider-managed-key"
        result["customer_managed_key_id"] = "my-isv-cmk-demo"
        result["tests"] = {
            "provider_managed_key_available": {"passed": True, "message": "Provider-managed key option exists"},
            "customer_managed_key_available": {"passed": True, "message": "Customer-managed key option exists"},
            "both_options_supported": {"passed": True, "message": "Both KMS encryption options are supported"},
        }
        result["success"] = True
    else:
        result["error"] = "Not implemented - replace with your platform's KMS encryption options test"

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
