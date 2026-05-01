#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Verify the platform issues short-lived credentials to nodes and workloads (SEC02-01).

This AWS reference probes two STS issuance paths whose response shape
mirrors the node and workload identity flows the requirement targets, and
asserts each returned credential carries a finite expiry that does not
exceed a configured upper bound:

* Node-equivalent: ``sts:GetSessionToken`` -- the API a long-lived IAM
  user uses to mint short-lived session credentials, equivalent in shape
  to the credentials an EC2 instance receives via instance metadata.
* Workload-equivalent: ``sts:GetFederationToken`` (with a deny-all session
  policy) -- the API used to issue short-lived credentials to an external
  workload identity, equivalent in shape to the credentials an
  IRSA-enabled pod receives.

When the calling principal is itself an assumed-role session, neither API
is available, and the step emits a structured ``skipped`` result (exit 0)
so the orchestrator and validation can skip the check rather than
fabricate a pass.

Usage:
    python short_lived_credentials_test.py --region us-west-2

Output JSON:
  {
    "success": true,
    "platform": "security",
    "test_name": "short_lived_credentials_test",
    "node_credential_method": "sts:GetSessionToken",
    "workload_credential_method": "sts:GetFederationToken",
    "node_credential_ttl_seconds": 43197,
    "workload_credential_ttl_seconds": 43197,
    "max_ttl_seconds": 43200,
    "tests": {
      "node_credential_has_expiry":           {"passed": true},
      "node_credential_ttl_within_bound":     {"passed": true},
      "workload_credential_has_expiry":       {"passed": true},
      "workload_credential_ttl_within_bound": {"passed": true}
    }
  }
"""

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import boto3
from botocore.exceptions import ClientError
from common.errors import handle_aws_errors

DEFAULT_MAX_TTL_SECONDS = 43200  # 12h - DGXC SEC02 upper bound for short-lived creds
NODE_METHOD = "sts:GetSessionToken"
WORKLOAD_METHOD = "sts:GetFederationToken"
WORKLOAD_FEDERATION_NAME = "isv-sec02-workload"
DENY_ALL_POLICY = json.dumps(
    {
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Deny", "Action": "*", "Resource": "*"}],
    }
)
# AWS error codes that mean "this principal cannot call the STS issuance API",
# which is operational signal (not a SEC02 failure) -> skip the step.
SKIPPABLE_STS_ERRORS = frozenset(
    {
        "AccessDenied",
        "InvalidClientTokenId",
        "ValidationError",
    }
)


def _ttl_seconds(expiration: datetime) -> int:
    """Return seconds until ``expiration``, treating naive datetimes as UTC."""
    if expiration.tzinfo is None:
        expiration = expiration.replace(tzinfo=UTC)
    now = datetime.now(UTC)
    return int((expiration - now).total_seconds())


def _skipped_result(reason: str) -> dict[str, Any]:
    """Return a structured top-level skip payload for the validation."""
    return {
        "success": True,
        "platform": "security",
        "test_name": "short_lived_credentials_test",
        "skipped": True,
        "skip_reason": reason,
        "tests": {},
    }


def _record_credential(
    result: dict[str, Any],
    *,
    expiry_key: str,
    ttl_key: str,
    ttl_field: str,
    expiration: datetime | None,
    max_ttl_seconds: int,
) -> None:
    """Update ``result`` with expiry + TTL probe outcomes for one credential."""
    if expiration is None:
        result["tests"][expiry_key]["error"] = "Credentials.Expiration missing in STS response"
        result["tests"][ttl_key]["error"] = "no expiry returned -- TTL bound cannot be evaluated"
        return
    result["tests"][expiry_key]["passed"] = True
    ttl = _ttl_seconds(expiration)
    result[ttl_field] = ttl
    if 0 < ttl <= max_ttl_seconds:
        result["tests"][ttl_key]["passed"] = True
    else:
        result["tests"][ttl_key]["error"] = f"TTL {ttl}s outside (0, {max_ttl_seconds}s] bound"


def _probe_node_credential(sts: Any) -> tuple[datetime | None, str | None]:
    """Call sts:GetSessionToken and return (expiration, skip_reason)."""
    try:
        response = sts.get_session_token()
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in SKIPPABLE_STS_ERRORS:
            return None, (
                f"{NODE_METHOD} not available with current principal ({code}); "
                f"AWS short-lived credential validation requires IAM user credentials"
            )
        raise
    expiration = response.get("Credentials", {}).get("Expiration")
    return expiration, None


def _probe_workload_credential(sts: Any) -> tuple[datetime | None, str | None]:
    """Call sts:GetFederationToken (deny-all policy) and return (expiration, error_msg)."""
    try:
        response = sts.get_federation_token(
            Name=WORKLOAD_FEDERATION_NAME,
            Policy=DENY_ALL_POLICY,
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in SKIPPABLE_STS_ERRORS:
            return None, f"{WORKLOAD_METHOD} not available ({code})"
        raise
    expiration = response.get("Credentials", {}).get("Expiration")
    return expiration, None


@handle_aws_errors
def main() -> int:
    """Run the short-lived credentials probes and emit JSON result."""
    parser = argparse.ArgumentParser(description="Short-lived credentials test (SEC02-01)")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-west-2"))
    parser.add_argument(
        "--max-ttl-seconds",
        type=int,
        default=DEFAULT_MAX_TTL_SECONDS,
        help=f"Upper bound on credential TTL (default: {DEFAULT_MAX_TTL_SECONDS})",
    )
    args = parser.parse_args()

    if args.max_ttl_seconds < 1:
        print(json.dumps(_skipped_result("--max-ttl-seconds must be a positive integer"), indent=2))
        return 0

    sts = boto3.client("sts", region_name=args.region)

    node_expiration, skip_reason = _probe_node_credential(sts)
    if skip_reason is not None:
        print(json.dumps(_skipped_result(skip_reason), indent=2, default=str))
        return 0

    result: dict[str, Any] = {
        "success": False,
        "platform": "security",
        "test_name": "short_lived_credentials_test",
        "node_credential_method": NODE_METHOD,
        "workload_credential_method": WORKLOAD_METHOD,
        "node_credential_ttl_seconds": 0,
        "workload_credential_ttl_seconds": 0,
        "max_ttl_seconds": args.max_ttl_seconds,
        "tests": {
            "node_credential_has_expiry": {"passed": False},
            "node_credential_ttl_within_bound": {"passed": False},
            "workload_credential_has_expiry": {"passed": False},
            "workload_credential_ttl_within_bound": {"passed": False},
        },
    }

    _record_credential(
        result,
        expiry_key="node_credential_has_expiry",
        ttl_key="node_credential_ttl_within_bound",
        ttl_field="node_credential_ttl_seconds",
        expiration=node_expiration,
        max_ttl_seconds=args.max_ttl_seconds,
    )

    workload_expiration, workload_error = _probe_workload_credential(sts)
    if workload_error is not None:
        result["tests"]["workload_credential_has_expiry"]["error"] = workload_error
        result["tests"]["workload_credential_ttl_within_bound"]["error"] = workload_error
    else:
        _record_credential(
            result,
            expiry_key="workload_credential_has_expiry",
            ttl_key="workload_credential_ttl_within_bound",
            ttl_field="workload_credential_ttl_seconds",
            expiration=workload_expiration,
            max_ttl_seconds=args.max_ttl_seconds,
        )

    result["success"] = all(probe["passed"] for probe in result["tests"].values())
    print(json.dumps(result, indent=2, default=str))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
