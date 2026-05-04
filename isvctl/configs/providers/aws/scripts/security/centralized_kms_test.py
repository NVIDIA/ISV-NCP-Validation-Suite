#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Verify encrypted resources reference KMS-backed keys.

The AWS reference samples encrypted EBS volumes and EKS secret-encryption
providers. It is intentionally bounded to avoid a long-running account-wide
audit.

Usage:
    python centralized_kms_test.py --region us-west-2
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

MAX_RESOURCES_PER_SERVICE = 25
REQUIRED_TESTS = [
    "kms_service_reachable",
    "kms_keys_present",
    "all_encrypted_resources_use_kms",
]


def _failed_tests(error: str) -> dict[str, dict[str, Any]]:
    """Build a failure result for every centralized-KMS probe."""
    return {name: {"passed": False, "error": error} for name in REQUIRED_TESTS}


def _base_result(region: str) -> dict[str, Any]:
    """Build the common result payload."""
    return {
        "success": False,
        "platform": "security",
        "test_name": "centralized_kms_test",
        "region": region,
        "kms_keys_total": 0,
        "encrypted_resources_inspected": 0,
        "non_kms_resources": 0,
        "non_kms_details": [],
        "inspection_errors": [],
        "tests": _failed_tests("Validation not executed"),
    }


def _list_kms_keys(kms: Any) -> list[dict[str, Any]]:
    """Return KMS keys visible in the region."""
    try:
        paginator = kms.get_paginator("list_keys")
    except Exception:
        return kms.list_keys().get("Keys", [])
    keys: list[dict[str, Any]] = []
    for page in paginator.paginate():
        keys.extend(page.get("Keys", []))
    return keys


def _normalize_kms_key_id(key_id: str) -> str:
    """Normalize common AWS managed-key shorthand to a KMS alias."""
    if key_id.startswith("aws/"):
        return f"alias/{key_id}"
    return key_id


def _resolve_kms_key(kms: Any, key_id: str | None) -> tuple[bool, str]:
    """Return whether ``key_id`` resolves through KMS."""
    if not key_id:
        return False, "missing KMS key id"
    try:
        metadata = kms.describe_key(KeyId=_normalize_kms_key_id(key_id))["KeyMetadata"]
    except ClientError as e:
        return False, str(e)
    key_state = metadata.get("KeyState", "Enabled")
    if key_state == "Disabled":
        return False, f"KMS key {key_id} is disabled"
    return True, f"KMS key {metadata.get('KeyId', key_id)} resolved"


def _record_non_kms(details: list[str], resource: str, reason: str) -> None:
    """Append a normalized non-KMS resource detail."""
    details.append(f"{resource}: {reason}")


def _inspect_ec2_volumes(ec2: Any, kms: Any, details: list[str]) -> int:
    """Inspect encrypted EBS volumes and return the number sampled."""
    inspected = 0
    kwargs = {"Filters": [{"Name": "encrypted", "Values": ["true"]}]}
    try:
        paginator = ec2.get_paginator("describe_volumes")
    except Exception:
        pages = [ec2.describe_volumes(**kwargs)]
    else:
        pages = paginator.paginate(**kwargs)

    for page in pages:
        for volume in page.get("Volumes", []):
            if inspected >= MAX_RESOURCES_PER_SERVICE:
                return inspected
            if volume.get("Encrypted") is not True:
                continue
            inspected += 1
            volume_id = volume.get("VolumeId", "<unknown-volume>")
            ok, message = _resolve_kms_key(kms, volume.get("KmsKeyId"))
            if not ok:
                _record_non_kms(details, f"ec2:{volume_id}", message)
    return inspected


def _inspect_eks_clusters(eks: Any, kms: Any, details: list[str]) -> int:
    """Inspect EKS secret-encryption providers and return the number sampled."""
    inspected = 0
    clusters_checked = 0
    next_token = ""
    while True:
        kwargs = {"nextToken": next_token} if next_token else {}
        response = eks.list_clusters(**kwargs)
        for cluster_name in response.get("clusters", []):
            if clusters_checked >= MAX_RESOURCES_PER_SERVICE:
                return inspected
            clusters_checked += 1
            cluster = eks.describe_cluster(name=cluster_name)["cluster"]
            encryption_config = cluster.get("encryptionConfig") or cluster.get("encryption_config") or []
            for item in encryption_config:
                key_arn = (item.get("provider") or {}).get("keyArn")
                if not key_arn:
                    continue
                inspected += 1
                ok, message = _resolve_kms_key(kms, key_arn)
                if not ok:
                    _record_non_kms(details, f"eks:{cluster_name}", message)
        next_token = response.get("nextToken", "")
        if not next_token:
            return inspected


def _run_centralized_kms_test(kms: Any, ec2: Any, eks: Any, region: str) -> dict[str, Any]:
    """Run SEC09-03 centralized-KMS checks with injected AWS clients."""
    result = _base_result(region)
    details: list[str] = []
    inspection_errors: list[str] = []

    try:
        keys = _list_kms_keys(kms)
    except Exception as e:
        result["error"] = str(e)
        result["tests"] = _failed_tests(str(e))
        return result

    result["kms_keys_total"] = len(keys)

    for service, inspector in (
        ("ec2", lambda: _inspect_ec2_volumes(ec2, kms, details)),
        ("eks", lambda: _inspect_eks_clusters(eks, kms, details)),
    ):
        try:
            result["encrypted_resources_inspected"] += inspector()
        except ClientError as e:
            inspection_errors.append(f"{service}: {e}")

    result["non_kms_details"] = details
    result["non_kms_resources"] = len(details)
    result["inspection_errors"] = inspection_errors
    kms_reachable = True
    kms_present = bool(keys)
    all_kms = not details and not inspection_errors
    if all_kms:
        all_kms_message = f"{result['encrypted_resources_inspected']} encrypted resource(s) resolved to KMS"
    elif details and inspection_errors:
        all_kms_message = (
            f"Encrypted resources without resolvable KMS keys: {details}; inspection errors: {inspection_errors}"
        )
    elif details:
        all_kms_message = f"Encrypted resources without resolvable KMS keys: {details}"
    else:
        all_kms_message = f"Inspection errors prevented full KMS verification: {inspection_errors}"
    result["tests"] = {
        "kms_service_reachable": {"passed": kms_reachable, "message": "KMS list_keys succeeded"},
        "kms_keys_present": {
            "passed": kms_present,
            "message" if kms_present else "error": (
                f"{len(keys)} KMS key(s) visible" if kms_present else "No KMS keys visible in the region"
            ),
        },
        "all_encrypted_resources_use_kms": {
            "passed": all_kms,
            "message" if all_kms else "error": all_kms_message,
        },
    }
    result["success"] = all(test.get("passed") for test in result["tests"].values())
    return result


@handle_aws_errors
def main() -> int:
    """Run centralized-KMS checks and emit JSON result."""
    parser = argparse.ArgumentParser(description="Centralized KMS test")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-west-2"))
    args = parser.parse_args()

    kms = boto3.client("kms", region_name=args.region)
    ec2 = boto3.client("ec2", region_name=args.region)
    eks = boto3.client("eks", region_name=args.region)
    result = _run_centralized_kms_test(kms, ec2, eks, args.region)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
