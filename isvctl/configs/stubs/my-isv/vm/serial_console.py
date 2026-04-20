#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Serial console access test - TEMPLATE (replace with your platform implementation).

This script retrieves serial console output from a running instance.
Read-only access is sufficient; interactive access is preferred but not required.

Required JSON output fields:
  {
    "success": true,
    "platform": "vm",
    "instance_id": "<id>",
    "console_available": true,
    "serial_access_enabled": true,
    "output_length": 4096,
    "output_snippet": "... last 500 chars ..."
  }

Usage:
    python serial_console.py --instance-id <id> --region <region>

Reference implementation: ../../aws/vm/serial_console.py
"""

import argparse
import json
import os
import sys
from typing import NoReturn

# ISVCTL_DEMO_MODE=1 enables demo-success output (used by `make demo-test`).
DEMO_MODE = os.environ.get("ISVCTL_DEMO_MODE") == "1"


def main() -> int:
    """Retrieve serial console output from a running instance and emit JSON."""
    parser = argparse.ArgumentParser(description="Serial console access test (template)")
    parser.add_argument("--instance-id", required=True, help="Instance ID")
    parser.add_argument("--region", required=True, help="Cloud region")

    def _arg_error(message: str) -> NoReturn:
        print(json.dumps({"success": False, "platform": "vm", "error": message}, indent=2))
        raise SystemExit(2)

    parser.error = _arg_error  # type: ignore[assignment]
    args = parser.parse_args()

    result: dict = {
        "success": False,
        "platform": "vm",
        "instance_id": args.instance_id,
        "console_available": False,
        "serial_access_enabled": False,
    }

    # TODO: Replace with your platform's serial console implementation
    if DEMO_MODE:
        result["instance_id"] = args.instance_id
        result["console_available"] = True
        result["serial_access_enabled"] = True
        result["output_length"] = 4096
        result["success"] = True
    else:
        result["error"] = "Not implemented - replace with your platform's serial console logic"

    print(json.dumps(result, indent=2))

    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
