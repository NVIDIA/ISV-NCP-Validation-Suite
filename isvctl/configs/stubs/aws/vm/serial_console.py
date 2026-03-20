#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Retrieve serial console output from an AWS EC2 instance (read-only).

Checks that serial console access is enabled for the account/region,
then retrieves the console output for the given instance.

Usage:
    python serial_console.py --instance-id i-xxx --region us-west-2

Output JSON:
{
    "success": true,
    "platform": "vm",
    "instance_id": "i-xxx",
    "console_available": true,
    "serial_access_enabled": true,
    "output_length": 4096,
    "output_snippet": "... last 500 chars of console output ..."
}
"""

import argparse
import json
import os
import sys
import time
from typing import Any

import boto3
from botocore.exceptions import ClientError


def check_serial_access(ec2: Any) -> dict[str, Any]:
    """Check if EC2 serial console access is enabled for the account."""
    result: dict[str, Any] = {"enabled": False}
    try:
        response = ec2.get_serial_console_access_status()
        result["enabled"] = response.get("SerialConsoleAccessEnabled", False)
    except ClientError as e:
        result["error"] = str(e)
    return result


def get_console_output(ec2: Any, instance_id: str, retries: int = 3) -> dict[str, Any]:
    """Retrieve the serial console output for an instance.

    Nitro-based instances may return empty output; retries with the
    ``Latest=True`` flag to fetch the most recent available output.
    """
    result: dict[str, Any] = {"available": False}
    try:
        for attempt in range(retries):
            response = ec2.get_console_output(InstanceId=instance_id, Latest=True)
            output = response.get("Output", "")

            if output:
                result["available"] = True
                result["output_length"] = len(output)
                result["output_snippet"] = output[-500:] if len(output) > 500 else output
                result["timestamp"] = str(response.get("Timestamp", ""))
                return result

            if attempt < retries - 1:
                time.sleep(10)

        result["output_length"] = 0
        result["message"] = "Console output empty (common on Nitro instances)"
    except ClientError as e:
        result["error"] = str(e)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Get EC2 serial console output")
    parser.add_argument("--instance-id", required=True, help="EC2 instance ID")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-west-2"))
    args = parser.parse_args()

    ec2 = boto3.client("ec2", region_name=args.region)

    result: dict[str, Any] = {
        "success": False,
        "platform": "vm",
        "instance_id": args.instance_id,
        "console_available": False,
        "serial_access_enabled": False,
    }

    try:
        # Check account-level serial console access
        access = check_serial_access(ec2)
        result["serial_access_enabled"] = access.get("enabled", False)
        if access.get("error"):
            result["serial_access_error"] = access["error"]

        # Get console output (works even if serial console SSH is disabled)
        console = get_console_output(ec2, args.instance_id)
        result["console_available"] = console.get("available", False)
        result["output_length"] = console.get("output_length", 0)

        if console.get("output_snippet"):
            result["output_snippet"] = console["output_snippet"]
        if console.get("timestamp"):
            result["timestamp"] = console["timestamp"]
        if console.get("error"):
            result["error"] = console["error"]

        # Success if console output is available OR serial access is enabled.
        # Nitro instances often return empty console output but the serial
        # console feature is still accessible via EC2 Instance Connect.
        result["success"] = result["console_available"] or result["serial_access_enabled"]

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
