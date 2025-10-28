#!/usr/bin/env python3
"""Create IAM user and access key for testing.

Output JSON:
{
    "success": true,
    "username": "isv-test-xxx",
    "access_key_id": "AKIA...",
    "secret_access_key": "xxx",
    "user_id": "arn:aws:iam::..."
}
"""

import argparse
import json
import os
import sys
import uuid
from typing import Any

import boto3
from botocore.exceptions import ClientError


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-west-2"))
    parser.add_argument("--username-prefix", default="isv-access-key-test")
    args = parser.parse_args()

    iam = boto3.client("iam")
    username = f"{args.username_prefix}-{uuid.uuid4().hex[:8]}"

    result: dict[str, Any] = {"success": False, "platform": "control_plane", "username": username}

    try:
        # Create user
        user_response = iam.create_user(UserName=username)
        result["user_id"] = user_response["User"]["Arn"]

        # Create access key
        key_response = iam.create_access_key(UserName=username)
        result["access_key_id"] = key_response["AccessKey"]["AccessKeyId"]
        result["secret_access_key"] = key_response["AccessKey"]["SecretAccessKey"]
        result["success"] = True

    except ClientError as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
