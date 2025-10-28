#!/usr/bin/env python3
"""Delete Resource Group (tenant).

Output JSON:
{
    "success": true,
    "deleted_group": "isv-tenant-xxx"
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--group-name", required=True)
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-west-2"))
    parser.add_argument("--skip-destroy", action="store_true")
    args = parser.parse_args()

    result: dict[str, Any] = {"success": False, "platform": "control_plane"}

    if args.skip_destroy:
        result["success"] = True
        result["skipped"] = True
        print(json.dumps(result, indent=2))
        return 0

    rg = boto3.client("resource-groups", region_name=args.region)

    try:
        rg.delete_group(GroupName=args.group_name)
        result["deleted_group"] = args.group_name
        result["success"] = True

    except ClientError as e:
        if e.response["Error"]["Code"] == "NotFoundException":
            result["success"] = True
            result["already_deleted"] = True
        else:
            result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
