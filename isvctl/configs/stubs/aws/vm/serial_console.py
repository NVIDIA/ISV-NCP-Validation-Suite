#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Retrieve serial console output from an AWS EC2 VM instance (read-only).

Usage:
    python serial_console.py --instance-id i-xxx --region us-west-2
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import boto3
from common.errors import handle_aws_errors
from common.serial_console import run_serial_console_check


@handle_aws_errors
def main() -> int:
    parser = argparse.ArgumentParser(description="Get EC2 VM serial console output")
    parser.add_argument("--instance-id", required=True, help="EC2 instance ID")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-west-2"))
    args = parser.parse_args()

    ec2 = boto3.client("ec2", region_name=args.region)
    _, exit_code = run_serial_console_check(ec2, args.instance_id, platform="vm")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
