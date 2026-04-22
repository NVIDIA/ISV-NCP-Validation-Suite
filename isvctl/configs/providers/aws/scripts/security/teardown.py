#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Security test teardown (AWS reference).

Each individual test script handles its own cleanup.  This teardown
step is a safety net that scans for leftover isv-sa-test-* IAM users
created by the SA credential test.

Usage:
    python teardown.py --region us-west-2
    python teardown.py --region us-west-2 --skip-destroy
"""

import argparse
import json
import os
import sys
from typing import Any

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

import boto3
from botocore.exceptions import ClientError
from common.errors import handle_aws_errors


@handle_aws_errors
def main() -> int:
    parser = argparse.ArgumentParser(description="Security test teardown")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-west-2"))
    parser.add_argument("--skip-destroy", action="store_true")
    args = parser.parse_args()

    result: dict[str, Any] = {
        "success": False,
        "platform": "security",
        "test_name": "teardown",
    }

    if args.skip_destroy:
        result["success"] = True
        result["skipped"] = True
        print(json.dumps(result, indent=2))
        return 0

    iam = boto3.client("iam", region_name=args.region)
    cleaned = 0

    try:
        paginator = iam.get_paginator("list_users")
        for page in paginator.paginate():
            for user in page["Users"]:
                name = user["UserName"]
                if not name.startswith("isv-sa-test-"):
                    continue
                # Delete access keys first
                try:
                    keys = iam.list_access_keys(UserName=name)["AccessKeyMetadata"]
                    for key in keys:
                        iam.delete_access_key(UserName=name, AccessKeyId=key["AccessKeyId"])
                except ClientError:
                    pass
                try:
                    iam.delete_user(UserName=name)
                    cleaned += 1
                except ClientError:
                    pass

        result["success"] = True
        result["resources_cleaned"] = cleaned
    except ClientError as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
