#!/usr/bin/env python3
"""Create IAM user for testing.

Usage:
    python create_user.py --username test-user

Output JSON:
{
    "success": true,
    "username": "test-user-abc123",
    "user_arn": "arn:aws:iam::123456789:user/test-user-abc123",
    "access_key_id": "AKIAIOSFODNN7EXAMPLE",
    "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
}
"""

import argparse
import json
import sys
import uuid

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

import boto3
from common.errors import handle_aws_errors


@handle_aws_errors
def main() -> int:
    parser = argparse.ArgumentParser(description="Create IAM user")
    parser.add_argument("--username", default="isv-test-user", help="Username prefix")
    parser.add_argument("--create-access-key", action="store_true", default=True)
    args = parser.parse_args()

    # Generate unique username
    suffix = str(uuid.uuid4())[:8]
    username = f"{args.username}-{suffix}"

    result = {
        "success": False,
        "platform": "iam",
        "username": username,
    }

    iam = boto3.client("iam")

    # Create user
    response = iam.create_user(UserName=username)
    result["user_arn"] = response["User"]["Arn"]
    result["user_id"] = response["User"]["UserId"]

    # Create access key
    if args.create_access_key:
        key_response = iam.create_access_key(UserName=username)
        result["access_key_id"] = key_response["AccessKey"]["AccessKeyId"]
        result["secret_access_key"] = key_response["AccessKey"]["SecretAccessKey"]

    result["success"] = True
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
