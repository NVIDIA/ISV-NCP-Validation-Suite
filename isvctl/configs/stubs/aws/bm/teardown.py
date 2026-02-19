#!/usr/bin/env python3
"""Teardown AWS EC2 bare-metal instance and associated resources.

Mirrors the VM teardown script but sets platform to "bm". The actual
EC2 API calls are identical (terminate, delete SG, delete key pair).

Usage:
    python teardown.py --instance-id i-xxx --region us-west-2

Output JSON:
{
    "success": true,
    "platform": "bm",
    "resources_destroyed": true,
    "deleted": {
        "instances": ["i-xxx"],
        "security_groups": ["sg-xxx"],
        "key_pairs": ["key-name"]
    }
}
"""

import argparse
import json
import os
import sys
import time

import boto3
from botocore.exceptions import ClientError, WaiterError


def main() -> int:
    """Terminate a bare-metal EC2 instance and clean up associated resources.

    Returns:
        0 on success, 1 on failure
    """
    parser = argparse.ArgumentParser(description="Teardown bare-metal EC2 instance")
    parser.add_argument("--instance-id", required=True, help="EC2 instance ID")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-west-2"))
    parser.add_argument("--delete-key-pair", action="store_true", help="Also delete key pair")
    parser.add_argument("--delete-security-group", action="store_true", help="Also delete security group")
    parser.add_argument("--skip-destroy", action="store_true", help="Skip actual destroy")
    args = parser.parse_args()

    result = {
        "success": False,
        "platform": "bm",
        "resources_destroyed": False,
        "deleted": {
            "instances": [],
            "security_groups": [],
            "key_pairs": [],
        },
    }

    if args.skip_destroy:
        result["success"] = True
        result["message"] = (
            f"Teardown skipped. Instance {args.instance_id} is still running. "
            f"To teardown later, unset AWS_BM_SKIP_TEARDOWN and rerun."
        )
        print(json.dumps(result, indent=2))
        return 0

    ec2 = boto3.client("ec2", region_name=args.region)

    sg_ids: list[str] = []
    key_name: str | None = None

    try:
        instances = ec2.describe_instances(InstanceIds=[args.instance_id])
        instance = instances["Reservations"][0]["Instances"][0]
        sg_ids = [sg["GroupId"] for sg in instance.get("SecurityGroups", [])]
        key_name = instance.get("KeyName")

        print(f"Terminating instance {args.instance_id}...", file=sys.stderr)
        ec2.terminate_instances(InstanceIds=[args.instance_id])
        result["deleted"]["instances"].append(args.instance_id)

        # Wait for termination -- bare-metal can take 15-20+ minutes.
        # If the waiter times out, that's OK: the terminate call succeeded
        # and AWS will finish it. We still proceed to clean up other resources.
        try:
            waiter = ec2.get_waiter("instance_terminated")
            waiter.wait(
                InstanceIds=[args.instance_id],
                WaiterConfig={"Delay": 30, "MaxAttempts": 50},
            )
            print("  Instance terminated", file=sys.stderr)
        except WaiterError:
            print(
                "  Waiter timed out, but terminate was initiated. AWS will finish asynchronously.",
                file=sys.stderr,
            )
            result.setdefault("warnings", []).append("Termination waiter timed out; instance is still shutting down")

    except ClientError as e:
        if e.response["Error"]["Code"] == "InvalidInstanceID.NotFound":
            result["message"] = "Instance not found (already terminated)"
        else:
            result["error"] = str(e)
            print(json.dumps(result, indent=2))
            return 1
    except Exception as e:
        result["error"] = str(e)
        print(json.dumps(result, indent=2))
        return 1

    # Always attempt SG and key pair cleanup, even if waiter timed out
    if args.delete_security_group and sg_ids:
        time.sleep(5)
        for sg_id in sg_ids:
            try:
                sg_info = ec2.describe_security_groups(GroupIds=[sg_id])
                if sg_info["SecurityGroups"] and sg_info["SecurityGroups"][0].get("GroupName") == "default":
                    continue
                ec2.delete_security_group(GroupId=sg_id)
                result["deleted"]["security_groups"].append(sg_id)
            except ClientError as e:
                error_code = e.response["Error"]["Code"]
                if error_code == "DependencyViolation":
                    result.setdefault("warnings", []).append(
                        f"SG {sg_id} still in use (instance shutting down); will be cleaned up by AWS"
                    )
                elif error_code not in ("InvalidGroup.NotFound", "CannotDelete"):
                    result.setdefault("warnings", []).append(f"Could not delete SG {sg_id}: {e}")

    if args.delete_key_pair and key_name:
        try:
            ec2.delete_key_pair(KeyName=key_name)
            result["deleted"]["key_pairs"].append(key_name)
            key_file = f"/tmp/{key_name}.pem"
            if os.path.exists(key_file):
                os.remove(key_file)
        except ClientError as e:
            result.setdefault("warnings", []).append(f"Could not delete key pair: {e}")

    result["success"] = True
    result["resources_destroyed"] = True
    result["message"] = "Bare-metal instance teardown completed"

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
