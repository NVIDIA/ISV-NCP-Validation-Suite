#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Reboot AWS EC2 instance and validate it comes back healthy.

Reboots the instance using the EC2 API, waits for it to return to running
state with passing status checks, then verifies SSH connectivity and captures
uptime to confirm the reboot actually happened.

Inspired by the reboot flow in setup.sh (lines 409-430).

Usage:
    python reboot_instance.py --instance-id i-xxx --region us-west-2 \
        --key-file /tmp/key.pem --public-ip 54.x.x.x

Output JSON:
{
    "success": true,
    "instance_id": "i-xxx",
    "state": "running",
    "public_ip": "54.x.x.x",
    "private_ip": "10.0.1.5",
    "key_file": "/tmp/key.pem",
    "ssh_user": "ubuntu",
    "reboot_initiated": true,
    "uptime_seconds": 45.2,
    "ssh_ready": true
}
"""

import argparse
import json
import os
import subprocess
import sys
import time
from typing import Any


def wait_for_ssh(
    host: str,
    user: str,
    key_file: str,
    max_attempts: int = 30,
    interval: int = 10,
) -> bool:
    """Wait for SSH to become available on the host.

    Args:
        host: Public IP or hostname
        user: SSH username
        key_file: Path to SSH private key
        max_attempts: Maximum number of connection attempts
        interval: Seconds between attempts

    Returns:
        True if SSH is ready, False if timed out
    """
    for attempt in range(1, max_attempts + 1):
        try:
            result = subprocess.run(
                [
                    "ssh",
                    "-o",
                    "StrictHostKeyChecking=no",
                    "-o",
                    "ConnectTimeout=5",
                    "-o",
                    "BatchMode=yes",
                    "-i",
                    key_file,
                    f"{user}@{host}",
                    "exit 0",
                ],
                capture_output=True,
                timeout=15,
            )
            if result.returncode == 0:
                print(f"  SSH ready after attempt {attempt}", file=sys.stderr)
                return True
        except (subprocess.TimeoutExpired, OSError):
            pass

        print(f"  Waiting for SSH... (attempt {attempt}/{max_attempts})", file=sys.stderr)
        time.sleep(interval)

    return False


def get_uptime_via_ssh(
    host: str,
    user: str,
    key_file: str,
) -> float | None:
    """Get system uptime in seconds via SSH.

    Args:
        host: Public IP or hostname
        user: SSH username
        key_file: Path to SSH private key

    Returns:
        Uptime in seconds, or None if command failed
    """
    try:
        result = subprocess.run(
            [
                "ssh",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "ConnectTimeout=10",
                "-o",
                "BatchMode=yes",
                "-i",
                key_file,
                f"{user}@{host}",
                "cat /proc/uptime | cut -d' ' -f1",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return float(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError, OSError):
        pass
    return None


def main() -> int:
    """Reboot an EC2 instance and wait for it to come back healthy.

    Performs the reboot via the EC2 API, waits for the instance to pass
    status checks, verifies SSH connectivity, and captures uptime to
    confirm the reboot actually occurred.

    Returns:
        0 on success, 1 on failure
    """
    parser = argparse.ArgumentParser(description="Reboot EC2 instance")
    parser.add_argument("--instance-id", required=True, help="EC2 instance ID")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-west-2"))
    parser.add_argument("--key-file", required=True, help="Path to SSH private key")
    parser.add_argument("--public-ip", required=True, help="Instance public IP")
    parser.add_argument("--ssh-user", default="ubuntu", help="SSH username")
    parser.add_argument(
        "--wait-before-check",
        type=int,
        default=60,
        help="Seconds to wait after reboot API call before checking (default: 60)",
    )
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
        "reboot_initiated": False,
        "ssh_ready": False,
    }

    try:
        # ============================================================
        # Step 1: Verify instance is currently running
        # ============================================================
        print("Verifying instance is running before reboot...", file=sys.stderr)
        instances = ec2.describe_instances(InstanceIds=[args.instance_id])
        instance = instances["Reservations"][0]["Instances"][0]
        current_state = instance["State"]["Name"]

        if current_state != "running":
            result["error"] = f"Instance is {current_state}, expected running"
            result["state"] = current_state
            print(json.dumps(result, indent=2))
            return 1

        # Capture pre-reboot uptime for comparison
        pre_uptime = get_uptime_via_ssh(args.public_ip, args.ssh_user, args.key_file)
        if pre_uptime is not None:
            result["pre_reboot_uptime"] = round(pre_uptime, 1)
            print(f"  Pre-reboot uptime: {pre_uptime:.0f}s", file=sys.stderr)

        # ============================================================
        # Step 2: Initiate reboot via EC2 API
        # ============================================================
        print(f"Rebooting instance {args.instance_id}...", file=sys.stderr)
        ec2.reboot_instances(InstanceIds=[args.instance_id])
        result["reboot_initiated"] = True
        print("  Reboot API call succeeded", file=sys.stderr)

        # ============================================================
        # Step 3: Wait for reboot to take effect
        # ============================================================
        print(
            f"Waiting {args.wait_before_check}s for reboot to take effect...",
            file=sys.stderr,
        )
        time.sleep(args.wait_before_check)

        # ============================================================
        # Step 4: Wait for instance status checks to pass
        # ============================================================
        print("Waiting for instance status checks...", file=sys.stderr)
        waiter = ec2.get_waiter("instance_status_ok")
        waiter.wait(
            InstanceIds=[args.instance_id],
            WaiterConfig={"Delay": 15, "MaxAttempts": 40},
        )
        print("  Instance status checks passed", file=sys.stderr)

        # ============================================================
        # Step 5: Get updated instance details
        # ============================================================
        instances = ec2.describe_instances(InstanceIds=[args.instance_id])
        instance = instances["Reservations"][0]["Instances"][0]

        result["state"] = instance["State"]["Name"]
        result["public_ip"] = instance.get("PublicIpAddress")
        result["private_ip"] = instance.get("PrivateIpAddress")

        public_ip = result["public_ip"] or args.public_ip

        # ============================================================
        # Step 6: Wait for SSH to be ready
        # ============================================================
        print("Waiting for SSH to be ready after reboot...", file=sys.stderr)
        ssh_ready = wait_for_ssh(public_ip, args.ssh_user, args.key_file)
        result["ssh_ready"] = ssh_ready

        if not ssh_ready:
            result["error"] = "SSH not ready after reboot"
            print("WARNING: SSH did not become ready after reboot", file=sys.stderr)
            print(json.dumps(result, indent=2))
            return 1

        # ============================================================
        # Step 7: Capture post-reboot uptime
        # ============================================================
        post_uptime = get_uptime_via_ssh(public_ip, args.ssh_user, args.key_file)
        if post_uptime is not None:
            result["uptime_seconds"] = round(post_uptime, 1)
            print(f"  Post-reboot uptime: {post_uptime:.0f}s", file=sys.stderr)

            # Validate that uptime is lower than pre-reboot (proves reboot happened)
            if pre_uptime is not None and post_uptime < pre_uptime:
                result["reboot_confirmed"] = True
                print("  Reboot confirmed (uptime reset)", file=sys.stderr)
            elif pre_uptime is not None:
                result["reboot_confirmed"] = False
                print(
                    f"  WARNING: Uptime did not decrease (pre={pre_uptime:.0f}s, post={post_uptime:.0f}s)",
                    file=sys.stderr,
                )
            else:
                # No pre-reboot uptime to compare against
                result["reboot_confirmed"] = post_uptime < 600  # <10 min = likely rebooted
                print(
                    f"  Reboot likely confirmed (uptime={post_uptime:.0f}s)",
                    file=sys.stderr,
                )

        result["success"] = True
        print("Reboot completed successfully!", file=sys.stderr)

    except Exception as e:
        result["error"] = str(e)
        print(f"ERROR: {e}", file=sys.stderr)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
