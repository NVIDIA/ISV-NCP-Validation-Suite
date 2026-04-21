#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Disable access key.

Output JSON:
{
    "success": true,
    "access_key_id": "AKIA...",
    "status": "Inactive"
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
    args = parser.parse_args()

    iam = boto3.client("iam")

    result: dict[str, Any] = {"success": False, "platform": "control_plane", "access_key_id": args.access_key_id}

    try:
        iam.update_access_key(
            UserName=args.username,
            AccessKeyId=args.access_key_id,
            Status="Inactive",
        )
        result["status"] = "Inactive"
        result["success"] = True

    except ClientError as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
