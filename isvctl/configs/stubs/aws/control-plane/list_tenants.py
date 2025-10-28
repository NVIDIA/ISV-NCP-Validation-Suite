#!/usr/bin/env python3
"""List Resource Groups (tenants).

Output JSON:
{
    "success": true,
    "groups": [
        {"tenant_name": "...", "tenant_id": "..."}
    ],
    "found_target": true,
    "target_group": "isv-tenant-xxx"
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
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-west-2"))
    parser.add_argument("--target-group", help="Group name to verify exists")
    args = parser.parse_args()

    rg = boto3.client("resource-groups", region_name=args.region)

    result: dict[str, Any] = {"success": False, "platform": "control_plane", "tenants": []}

    try:
        response = rg.list_groups()
        for g in response.get("GroupIdentifiers", []):
            result["tenants"].append({"tenant_name": g["GroupName"], "tenant_id": g["GroupArn"]})

        if args.target_group:
            result["target_tenant"] = args.target_group
            result["found_target"] = any(t["tenant_name"] == args.target_group for t in result["tenants"])

        result["count"] = len(result["tenants"])
        result["success"] = True

    except ClientError as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
