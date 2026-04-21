#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Start a stopped AWS EC2 instance and verify it returns to running state.

Starts the instance using the EC2 API, waits for it to return to running
state with passing status checks, then verifies SSH connectivity.

Usage:
    python start_instance.py --instance-id i-xxx --region us-west-2 \\
        --key-file /tmp/key.pem --public-ip 54.x.x.x

Output JSON:
{
    "success": true,
    "platform": "vm",
    "instance_id": "i-xxx",
    "state": "running",
    "public_ip": "54.x.x.x",
    "private_ip": "10.0.1.5",
    "key_file": "/tmp/key.pem",
    "ssh_user": "ubuntu",
    "start_initiated": true,
    "ssh_ready": true,
    "region": "us-west-2"
}
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.ssh_utils import wait_for_ssh


def main() -> int:
    """Start a stopped EC2 instance and wait for it to be healthy.

    Returns:
        0 on success, 1 on failure
    """
    parser = argparse.ArgumentParser(description="Start stopped EC2 instance")
    parser.add_argument("--instance-id", required=True, help="EC2 instance ID")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-west-2"))
    parser.add_argument("--key-file", required=True, help="Path to SSH private key")
    parser.add_argument("--public-ip", required=True, help="Instance public IP")
    parser.add_argument("--ssh-user", default="ubuntu", help="SSH username")
    args = parser.parse_args()

    import boto3

    ec2 = boto3.client("ec2", region_name=args.region)

    result: dict[str, Any] = {
        "success": False,
        "platform": "vm",
        "instance_id": args.instance_id,
        "region": args.region,
        "key_file": args.key_file,
        "ssh_user": args.ssh_user,
        "start_initiated": False,
        "ssh_ready": False,
    }

    try:
        # ============================================================
        # Step 1: Verify instance is currently stopped
        # ============================================================
        print("Verifying instance is stopped before start...", file=sys.stderr)
        instances = ec2.describe_instances(InstanceIds=[args.instance_id])
        instance = instances["Reservations"][0]["Instances"][0]
        current_state = instance["State"]["Name"]

        if current_state != "stopped":
            result["error"] = f"Instance is {current_state}, expected stopped"
            result["state"] = current_state
            print(json.dumps(result, indent=2))
            return 1

        # ============================================================
        # Step 2: Start the instance via EC2 API
        # ============================================================
        print(f"Starting instance {args.instance_id}...", file=sys.stderr)
        ec2.start_instances(InstanceIds=[args.instance_id])
        result["start_initiated"] = True
        print("  Start API call succeeded", file=sys.stderr)

        # ============================================================
        # Step 3: Wait for instance status checks to pass
        # ============================================================
        print("Waiting for instance status checks...", file=sys.stderr)
        waiter = ec2.get_waiter("instance_status_ok")
        waiter.wait(
            InstanceIds=[args.instance_id],
            WaiterConfig={"Delay": 15, "MaxAttempts": 40},
        )
        print("  Instance status checks passed", file=sys.stderr)

        # ============================================================
        # Step 4: Get updated instance details
        # ============================================================
        instances = ec2.describe_instances(InstanceIds=[args.instance_id])
        instance = instances["Reservations"][0]["Instances"][0]
        result["state"] = instance["State"]["Name"]
        result["public_ip"] = instance.get("PublicIpAddress") or args.public_ip
        result["private_ip"] = instance.get("PrivateIpAddress")

        # ============================================================
        # Step 5: Wait for SSH to be ready
        # ============================================================
        print("Waiting for SSH to be ready...", file=sys.stderr)
        ssh_ready = wait_for_ssh(result["public_ip"], args.ssh_user, args.key_file, max_attempts=30, interval=10)
        result["ssh_ready"] = ssh_ready

        if not ssh_ready:
            result["error"] = "SSH not ready after start"
            print("WARNING: SSH did not become ready after start", file=sys.stderr)
            print(json.dumps(result, indent=2))
            return 1

        result["success"] = True
        print("Start completed successfully!", file=sys.stderr)

    except Exception as e:
        result["error"] = str(e)
        print(f"ERROR: {e}", file=sys.stderr)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
