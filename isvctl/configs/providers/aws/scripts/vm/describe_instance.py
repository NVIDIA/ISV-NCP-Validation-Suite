#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Describe a running AWS EC2 VM instance.

Lightweight test-phase step that fetches current instance state and
passes through SSH connection info. Validations (SSH, GPU, host OS)
bind to this step so they run in the test phase rather than setup,
ensuring teardown always runs even if tests fail.

Additionally, running these checks against the post-reboot state proves
the host survived the full stop/start/reboot lifecycle (driver, docker,
pinning, etc.), which a launch-time anchor cannot prove.

Usage:
    python describe_instance.py --instance-id i-xxx --region us-west-2 \
        --key-file /tmp/key.pem

Output JSON:
{
    "success": true,
    "platform": "vm",
    "instance_id": "i-xxx",
    "instance_type": "g5.xlarge",
    "state": "running",
    "public_ip": "54.x.x.x",
    "private_ip": "10.0.1.5",
    "key_file": "/tmp/key.pem",
    "ssh_user": "ubuntu"
}
"""

import argparse
import json
import os
import sys
from typing import Any

import boto3
from botocore.exceptions import ClientError


def main() -> int:
    """Describe a VM EC2 instance and return its current state.

    Returns:
        0 on success, 1 on failure
    """
    parser = argparse.ArgumentParser(description="Describe VM EC2 instance")
    parser.add_argument("--instance-id", required=True, help="EC2 instance ID")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-west-2"))
    parser.add_argument("--key-file", required=True, help="Path to SSH private key")
    parser.add_argument("--ssh-user", default="ubuntu", help="SSH username")
    args = parser.parse_args()

    ec2 = boto3.client("ec2", region_name=args.region)

    result: dict[str, Any] = {
        "success": False,
        "platform": "vm",
        "instance_id": args.instance_id,
        "region": args.region,
        "key_file": args.key_file,
        "ssh_user": args.ssh_user,
    }

    try:
        instances = ec2.describe_instances(InstanceIds=[args.instance_id])
        instance = instances["Reservations"][0]["Instances"][0]

        result["state"] = instance["State"]["Name"]
        result["instance_type"] = instance.get("InstanceType")
        result["public_ip"] = instance.get("PublicIpAddress")
        result["private_ip"] = instance.get("PrivateIpAddress")
        result["vpc_id"] = instance.get("VpcId")
        result["subnet_id"] = instance.get("SubnetId")
        result["availability_zone"] = instance.get("Placement", {}).get("AvailabilityZone")
        result["launch_time"] = instance.get("LaunchTime", "").isoformat() if instance.get("LaunchTime") else None
        result["success"] = True

    except ClientError as e:
        if e.response["Error"]["Code"] == "InvalidInstanceID.NotFound":
            result["error"] = f"Instance {args.instance_id} not found"
        else:
            result["error"] = str(e)
    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2, default=str))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
