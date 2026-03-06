#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Get Resource Group (tenant) info.

Output JSON:
{
    "success": true,
    "tenant_name": "isv-tenant-xxx",
    "tenant_id": "arn:aws:...",
    "description": "...",
    "tags": {"key": "value"}
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
    args = parser.parse_args()

    rg = boto3.client("resource-groups", region_name=args.region)

    result: dict[str, Any] = {"success": False, "platform": "control_plane", "tenant_name": args.group_name}

    try:
        response = rg.get_group(GroupName=args.group_name)
        group = response["Group"]
        result["tenant_id"] = group["GroupArn"]
        result["description"] = group.get("Description", "")

        # Get tags
        tags_response = rg.get_tags(Arn=group["GroupArn"])
        result["tags"] = tags_response.get("Tags", {})

        result["success"] = True

    except ClientError as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
