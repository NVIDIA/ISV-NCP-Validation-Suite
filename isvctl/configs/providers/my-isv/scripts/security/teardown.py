#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Security test teardown - TEMPLATE (replace with your platform implementation).

Cleans up any resources created during security validation tests.

Usage:
    python teardown.py --region <region>
    python teardown.py --region <region> --skip-destroy
"""

import argparse
import json
import os
import sys
from typing import Any

DEMO_MODE = os.environ.get("ISVCTL_DEMO_MODE") == "1"


def main() -> int:
    """Security teardown (template) and emit structured JSON result."""
    parser = argparse.ArgumentParser(description="Security test teardown (template)")
    parser.add_argument("--region", required=True, help="Cloud region")
    parser.add_argument(
        "--skip-destroy",
        action="store_true",
        help="Skip actual resource destruction",
    )
    args = parser.parse_args()

    result: dict[str, Any] = {
        "success": False,
        "platform": "security",
        "test_name": "teardown",
    }

    if args.skip_destroy:
        result["success"] = True
        result["skipped"] = True
        print(json.dumps(result, indent=2))
        return 0

    if DEMO_MODE:
        result["success"] = True
        result["resources_cleaned"] = 0
    else:
        result["error"] = "Not implemented - replace with your platform's security teardown"

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
