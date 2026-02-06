#!/usr/bin/env python3
"""Delete IAM user and associated resources.

Usage:
    python delete_user.py --username test-user-abc123

Output JSON:
{
    "success": true,
    "resources_destroyed": true,
    "deleted": {
        "access_keys": ["AKIA..."],
        "user": "test-user-abc123"
    }
}
"""

import argparse
import json
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

import boto3
from botocore.exceptions import ClientError
from common.errors import handle_aws_errors


@handle_aws_errors
def main() -> int:
    parser = argparse.ArgumentParser(description="Delete IAM user")
    parser.add_argument("--username", required=True, help="IAM username to delete")
    parser.add_argument("--skip-destroy", action="store_true", help="Skip actual destroy")
    args = parser.parse_args()

    result = {
        "success": False,
        "platform": "iam",
        "resources_destroyed": False,
        "resources_deleted": [],
        "deleted": {
            "access_keys": [],
            "policies": [],
            "user": None,
        },
    }

    if args.skip_destroy:
        result["success"] = True
        result["message"] = "Destroy skipped (--skip-destroy flag)"
        print(json.dumps(result, indent=2))
        return 0

    iam = boto3.client("iam")

    try:
        # Delete access keys
        keys = iam.list_access_keys(UserName=args.username)
        for key in keys.get("AccessKeyMetadata", []):
            iam.delete_access_key(
                UserName=args.username,
                AccessKeyId=key["AccessKeyId"],
            )
            result["deleted"]["access_keys"].append(key["AccessKeyId"])
            result["resources_deleted"].append(f"access_key:{key['AccessKeyId']}")

        # Detach managed policies
        policies = iam.list_attached_user_policies(UserName=args.username)
        for policy in policies.get("AttachedPolicies", []):
            iam.detach_user_policy(
                UserName=args.username,
                PolicyArn=policy["PolicyArn"],
            )
            result["deleted"]["policies"].append(policy["PolicyArn"])

        # Delete inline policies
        inline_policies = iam.list_user_policies(UserName=args.username)
        for policy_name in inline_policies.get("PolicyNames", []):
            iam.delete_user_policy(
                UserName=args.username,
                PolicyName=policy_name,
            )

        # Delete user
        iam.delete_user(UserName=args.username)
        result["deleted"]["user"] = args.username
        result["resources_deleted"].append(f"user:{args.username}")

        result["success"] = True
        result["resources_destroyed"] = True
        result["message"] = "User deleted successfully"

    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchEntity":
            result["success"] = True
            result["message"] = "User not found (already deleted)"
        else:
            raise  # Let handle_aws_errors catch it

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
