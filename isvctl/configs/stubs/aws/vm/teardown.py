#!/usr/bin/env python3
"""Teardown AWS EC2 instance and associated resources.

Usage:
    python teardown.py --instance-id i-xxx --region us-west-2

Output JSON:
{
    "success": true,
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
from botocore.exceptions import ClientError


def main() -> int:
    parser = argparse.ArgumentParser(description="Teardown EC2 instance")
    parser.add_argument("--instance-id", required=True, help="EC2 instance ID")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-west-2"))
    parser.add_argument("--delete-key-pair", action="store_true", help="Also delete key pair")
    parser.add_argument("--delete-security-group", action="store_true", help="Also delete security group")
    parser.add_argument("--skip-destroy", action="store_true", help="Skip actual destroy")
    args = parser.parse_args()

    result = {
        "success": False,
        "platform": "vm",
        "resources_destroyed": False,
        "deleted": {
            "instances": [],
            "security_groups": [],
            "key_pairs": [],
        },
    }

    if args.skip_destroy:
        result["success"] = True
        result["message"] = "Destroy skipped (--skip-destroy flag)"
        print(json.dumps(result, indent=2))
        return 0

    ec2 = boto3.client("ec2", region_name=args.region)

    try:
        # Get instance details before termination
        instances = ec2.describe_instances(InstanceIds=[args.instance_id])
        instance = instances["Reservations"][0]["Instances"][0]
        sg_ids = [sg["GroupId"] for sg in instance.get("SecurityGroups", [])]
        key_name = instance.get("KeyName")

        # Terminate instance
        ec2.terminate_instances(InstanceIds=[args.instance_id])

        # Wait for termination
        waiter = ec2.get_waiter("instance_terminated")
        waiter.wait(InstanceIds=[args.instance_id])
        result["deleted"]["instances"].append(args.instance_id)

        # Delete security groups if requested
        if args.delete_security_group and sg_ids:
            time.sleep(5)  # Wait for instance to fully release SG
            for sg_id in sg_ids:
                try:
                    # Check if it's the default SG (can't be deleted)
                    sg_info = ec2.describe_security_groups(GroupIds=[sg_id])
                    if sg_info["SecurityGroups"] and sg_info["SecurityGroups"][0].get("GroupName") == "default":
                        continue  # Skip default SG
                    ec2.delete_security_group(GroupId=sg_id)
                    result["deleted"]["security_groups"].append(sg_id)
                except ClientError as e:
                    error_code = e.response["Error"]["Code"]
                    if error_code not in ("InvalidGroup.NotFound", "CannotDelete"):
                        result.setdefault("warnings", []).append(f"Could not delete SG {sg_id}: {e}")

        # Delete key pair if requested
        if args.delete_key_pair and key_name:
            try:
                ec2.delete_key_pair(KeyName=key_name)
                result["deleted"]["key_pairs"].append(key_name)
                # Also delete local key file
                key_file = f"/tmp/{key_name}.pem"
                if os.path.exists(key_file):
                    os.remove(key_file)
            except ClientError as e:
                result.setdefault("warnings", []).append(f"Could not delete key pair: {e}")

        result["success"] = True
        result["resources_destroyed"] = True
        result["message"] = "Instance terminated successfully"

    except ClientError as e:
        if e.response["Error"]["Code"] == "InvalidInstanceID.NotFound":
            result["success"] = True
            result["message"] = "Instance not found (already terminated)"
        else:
            result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
