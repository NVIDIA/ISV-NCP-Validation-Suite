#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Verify out-of-cluster service accounts can authenticate with long-lived credentials.

AWS reference implementation: creates a temporary IAM user with
programmatic access (long-lived access key), authenticates with
STS GetCallerIdentity, then cleans up.

Usage:
    python sa_credential_test.py --region us-west-2

Output JSON:
  {
    "success": true,
    "platform": "security",
    "test_name": "sa_credential_test",
    "authenticated": true,
    "credential_type": "access_key",
    "identity": "arn:aws:iam::123456789012:user/isv-sa-test-xxxx",
    "expires_at": null
  }
"""

import argparse
import json
import os
import sys
import uuid
from typing import Any

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

import boto3
from botocore.exceptions import ClientError
from common.errors import handle_aws_errors


@handle_aws_errors
def main() -> int:
    parser = argparse.ArgumentParser(description="Service account credential test")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-west-2"))
    args = parser.parse_args()

    iam = boto3.client("iam", region_name=args.region)

    result: dict[str, Any] = {
        "success": False,
        "platform": "security",
        "test_name": "sa_credential_test",
        "authenticated": False,
        "credential_type": "",
        "identity": "",
        "expires_at": None,
    }

    username = f"isv-sa-test-{uuid.uuid4().hex[:8]}"
    access_key_id = None

    try:
        # Create a temporary IAM user (simulates out-of-cluster SA)
        iam.create_user(
            UserName=username,
            Tags=[{"Key": "CreatedBy", "Value": "isvtest"}],
        )

        # Create long-lived access key
        key_response = iam.create_access_key(UserName=username)
        access_key_id = key_response["AccessKey"]["AccessKeyId"]
        secret_key = key_response["AccessKey"]["SecretAccessKey"]

        result["credential_type"] = "access_key"

        # Authenticate with the new key via STS
        sts = boto3.client(
            "sts",
            region_name=args.region,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_key,
        )

        # STS may need a moment for IAM propagation
        import time

        for attempt in range(5):
            try:
                identity = sts.get_caller_identity()
                result["authenticated"] = True
                result["identity"] = identity["Arn"]
                result["success"] = True
                break
            except ClientError as e:
                code = e.response.get("Error", {}).get("Code", "")
                if code == "InvalidClientTokenId" and attempt < 4:
                    time.sleep(2)
                    continue
                raise

    except ClientError as e:
        result["error"] = str(e)
    finally:
        # Cleanup: delete key then user
        if access_key_id:
            try:
                iam.delete_access_key(UserName=username, AccessKeyId=access_key_id)
            except ClientError:
                pass
        try:
            iam.delete_user(UserName=username)
        except ClientError:
            pass

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
