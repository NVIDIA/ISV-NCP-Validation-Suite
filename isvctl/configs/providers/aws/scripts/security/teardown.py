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


def _user_has_isvtest_tag(iam: Any, username: str) -> bool:
    """Return True when the IAM user is tagged as owned by isvtest."""
    try:
        kwargs: dict[str, Any] = {"UserName": username}
        while True:
            response = iam.list_user_tags(**kwargs)
            for tag in response.get("Tags", []):
                if tag.get("Key") == "CreatedBy" and tag.get("Value") == "isvtest":
                    return True
            if not response.get("IsTruncated"):
                return False
            kwargs["Marker"] = response.get("Marker")
    except ClientError:
        return False


def _cleanup_owned_user(iam: Any, username: str) -> list[str]:
    """Delete one owned IAM user and its access keys, returning cleanup errors."""
    cleanup_errors: list[str] = []
    keys: list[dict[str, Any]] = []

    try:
        keys = iam.list_access_keys(UserName=username)["AccessKeyMetadata"]
    except ClientError as e:
        cleanup_errors.append(f"list access keys for {username}: {e}")

    for key in keys:
        access_key_id = key["AccessKeyId"]
        try:
            iam.delete_access_key(UserName=username, AccessKeyId=access_key_id)
        except ClientError as e:
            cleanup_errors.append(f"delete access key {access_key_id} for {username}: {e}")

    try:
        iam.delete_user(UserName=username)
    except ClientError as e:
        cleanup_errors.append(f"delete user {username}: {e}")

    return cleanup_errors


@handle_aws_errors
def main() -> int:
    """Clean up leftover security test resources created by isvtest."""
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
    skipped_unowned = 0
    failed_resources: list[dict[str, Any]] = []

    try:
        paginator = iam.get_paginator("list_users")
        for page in paginator.paginate():
            for user in page["Users"]:
                name = user["UserName"]
                if not name.startswith("isv-sa-test-"):
                    continue
                if not _user_has_isvtest_tag(iam, name):
                    skipped_unowned += 1
                    continue
                cleanup_errors = _cleanup_owned_user(iam, name)
                if cleanup_errors:
                    failed_resources.append({"username": name, "errors": cleanup_errors})
                else:
                    cleaned += 1

        result["resources_cleaned"] = cleaned
        result["resources_skipped_unowned"] = skipped_unowned
        if failed_resources:
            result["success"] = False
            result["resources_failed"] = failed_resources
            result["error"] = f"Failed to clean up {len(failed_resources)} owned IAM user(s): " + "; ".join(
                f"{item['username']}: {', '.join(item['errors'])}" for item in failed_resources
            )
        else:
            result["success"] = True
    except ClientError as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
