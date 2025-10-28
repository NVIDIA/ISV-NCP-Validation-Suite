#!/usr/bin/env python3
"""Delete access key and user.

Output JSON:
{
    "success": true,
    "deleted_key": "AKIA...",
    "deleted_user": "isv-test-xxx"
}
"""

import argparse
import json
import sys
from typing import Any

import boto3
from botocore.exceptions import ClientError


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True)
    parser.add_argument("--access-key-id", required=True)
    parser.add_argument("--skip-destroy", action="store_true")
    args = parser.parse_args()

    result: dict[str, Any] = {"success": False, "platform": "control_plane"}

    if args.skip_destroy:
        result["success"] = True
        result["skipped"] = True
        print(json.dumps(result, indent=2))
        return 0

    iam = boto3.client("iam")

    try:
        # Delete access key
        iam.delete_access_key(UserName=args.username, AccessKeyId=args.access_key_id)
        result["deleted_key"] = args.access_key_id

        # Delete user
        iam.delete_user(UserName=args.username)
        result["deleted_user"] = args.username
        result["success"] = True

    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchEntity":
            result["success"] = True
            result["already_deleted"] = True
        else:
            result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
