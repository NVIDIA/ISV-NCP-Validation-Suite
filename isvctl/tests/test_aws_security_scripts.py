# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Tests for AWS security reference scripts."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from botocore.exceptions import ClientError

ISVCTL_ROOT = Path(__file__).resolve().parents[1]
AWS_SECURITY_SCRIPTS = ISVCTL_ROOT / "configs" / "providers" / "aws" / "scripts" / "security"


def _load_security_script(script_name: str) -> ModuleType:
    """Load an AWS security script as a module for direct helper testing."""
    script_path = AWS_SECURITY_SCRIPTS / script_name
    spec = importlib.util.spec_from_file_location(f"test_{script_path.stem}", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _client_error(operation_name: str, code: str = "AccessDenied", message: str = "denied") -> ClientError:
    """Create a botocore ClientError for fake AWS client failures."""
    return ClientError({"Error": {"Code": code, "Message": message}}, operation_name)


class FakeEksClient:
    """Small fake for the EKS client calls used by api_endpoint_test."""

    def __init__(self, cluster_configs: dict[str, dict[str, Any]]) -> None:
        """Store fake cluster configs keyed by cluster name."""
        self.cluster_configs = cluster_configs

    def list_clusters(self) -> dict[str, list[str]]:
        """Return fake cluster names."""
        return {"clusters": list(self.cluster_configs)}

    def describe_cluster(self, name: str) -> dict[str, dict[str, dict[str, Any]]]:
        """Return fake cluster config for a cluster name."""
        return {"cluster": {"resourcesVpcConfig": self.cluster_configs[name]}}


def _patch_eks_client(monkeypatch: pytest.MonkeyPatch, module: ModuleType, eks: FakeEksClient) -> None:
    """Patch boto3.client to return a fake EKS client."""

    def fake_client(service_name: str, region_name: str | None = None) -> FakeEksClient:
        """Return the fake EKS client for EKS requests."""
        assert service_name == "eks"
        assert region_name == "us-west-2"
        return eks

    monkeypatch.setattr(module.boto3, "client", fake_client)


def test_eks_private_check_fails_public_private_cluster_with_world_open_cidr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dual endpoint EKS clusters still fail when public access is world-open."""
    module = _load_security_script("api_endpoint_test.py")
    eks = FakeEksClient(
        {
            "wide-open": {
                "endpointPublicAccess": True,
                "endpointPrivateAccess": True,
                "publicAccessCidrs": ["0.0.0.0/0"],
            }
        }
    )
    _patch_eks_client(monkeypatch, module, eks)

    result = module._check_eks_private("us-west-2")

    assert result["passed"] is False
    assert "open to the internet" in result["error"]


def test_eks_private_check_accepts_dual_endpoint_with_restricted_public_cidr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dual endpoint EKS clusters pass when public CIDRs are restricted."""
    module = _load_security_script("api_endpoint_test.py")
    eks = FakeEksClient(
        {
            "restricted": {
                "endpointPublicAccess": True,
                "endpointPrivateAccess": True,
                "publicAccessCidrs": ["203.0.113.0/24"],
            }
        }
    )
    _patch_eks_client(monkeypatch, module, eks)

    result = module._check_eks_private("us-west-2")

    assert result["passed"] is True


def test_eks_private_check_fails_public_only_cluster_even_with_restricted_cidr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Public-only EKS clusters fail even if public CIDRs are restricted."""
    module = _load_security_script("api_endpoint_test.py")
    eks = FakeEksClient(
        {
            "public-only": {
                "endpointPublicAccess": True,
                "endpointPrivateAccess": False,
                "publicAccessCidrs": ["203.0.113.0/24"],
            }
        }
    )
    _patch_eks_client(monkeypatch, module, eks)

    result = module._check_eks_private("us-west-2")

    assert result["passed"] is False
    assert "public-only" in result["error"]


class FakeEc2Paginator:
    """Fake EC2 paginator returning configured pages."""

    def __init__(self, pages: list[dict[str, Any]]) -> None:
        """Store pages to return from paginate."""
        self.pages = pages
        self.calls: list[dict[str, Any]] = []

    def paginate(self, **kwargs: Any) -> list[dict[str, Any]]:
        """Return all configured pages and record the pagination filters."""
        self.calls.append(kwargs)
        return self.pages


class FakeBmcEc2:
    """Fake EC2 client for BMC isolation checks."""

    def __init__(self) -> None:
        """Initialize paginated EC2 responses."""
        self.paginators = {
            "describe_route_tables": FakeEc2Paginator(
                [
                    {"RouteTables": [{"RouteTableId": "rtb-first", "Routes": []}]},
                    {
                        "RouteTables": [
                            {
                                "RouteTableId": "rtb-second",
                                "Routes": [{"DestinationCidrBlock": "169.254.0.0/16"}],
                            }
                        ]
                    },
                ]
            ),
            "describe_security_groups": FakeEc2Paginator(
                [
                    {"SecurityGroups": [{"GroupId": "sg-first", "IpPermissionsEgress": []}]},
                    {
                        "SecurityGroups": [
                            {
                                "GroupId": "sg-second",
                                "IpPermissionsEgress": [{"IpRanges": [{"CidrIp": "198.18.0.0/15"}]}],
                            }
                        ]
                    },
                ]
            ),
            "describe_vpcs": FakeEc2Paginator([{"Vpcs": [{"VpcId": "vpc-nondefault"}]}]),
        }

    def get_paginator(self, operation_name: str) -> FakeEc2Paginator:
        """Return a fake paginator for the requested EC2 operation."""
        return self.paginators[operation_name]

    def describe_route_tables(self, **kwargs: Any) -> dict[str, list[dict[str, Any]]]:
        """Return only the first route table page to expose missing pagination."""
        return self.paginators["describe_route_tables"].pages[0]

    def describe_security_groups(self, **kwargs: Any) -> dict[str, list[dict[str, Any]]]:
        """Return only the first security group page to expose missing pagination."""
        return self.paginators["describe_security_groups"].pages[0]

    def describe_vpcs(self, **kwargs: Any) -> dict[str, list[dict[str, str]]]:
        """Return no default VPC for the legacy lookup path."""
        assert kwargs == {"Filters": [{"Name": "is-default", "Values": ["true"]}]}
        return {"Vpcs": []}


def test_bmc_checks_scan_paginated_route_tables_and_security_groups() -> None:
    """BMC route and SG checks inspect every EC2 paginator page."""
    module = _load_security_script("bmc_isolation_test.py")
    ec2 = FakeBmcEc2()

    route_result = module._check_route_tables(ec2, "vpc-nondefault")
    sg_result = module._check_sg_no_bmc_egress(ec2, "vpc-nondefault")

    assert route_result["passed"] is False
    assert "rtb-second" in route_result["error"]
    assert sg_result["passed"] is False
    assert "sg-second" in sg_result["error"]
    assert ec2.paginators["describe_route_tables"].calls == [
        {"Filters": [{"Name": "vpc-id", "Values": ["vpc-nondefault"]}]}
    ]
    assert ec2.paginators["describe_security_groups"].calls == [
        {"Filters": [{"Name": "vpc-id", "Values": ["vpc-nondefault"]}]}
    ]


def test_bmc_main_scans_non_default_vpcs_when_no_vpc_id(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """BMC validation checks non-default VPCs instead of auto-passing without a default VPC."""
    module = _load_security_script("bmc_isolation_test.py")
    ec2 = FakeBmcEc2()

    def fake_client(service_name: str, **kwargs: Any) -> FakeBmcEc2:
        """Return the fake EC2 client."""
        assert service_name == "ec2"
        return ec2

    monkeypatch.setattr(module.boto3, "client", fake_client)
    monkeypatch.setattr(module.sys, "argv", ["bmc_isolation_test.py", "--region", "us-west-2"])

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["success"] is False
    assert payload["tests"]["probe_bmc_from_tenant"]["passed"] is False
    assert "vpc-nondefault" in payload["tests"]["probe_bmc_from_tenant"]["error"]
    assert ec2.paginators["describe_vpcs"].calls == [{}]


class FakeIamTags:
    """Small fake for IAM list_user_tags responses."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        """Store responses returned by list_user_tags."""
        self.responses = responses

    def list_user_tags(self, **kwargs: Any) -> dict[str, Any]:
        """Return the next fake list_user_tags response."""
        assert kwargs["UserName"] == "isv-sa-test-1234"
        return self.responses.pop(0)


def test_teardown_only_treats_created_by_isvtest_users_as_owned() -> None:
    """Teardown ownership requires the CreatedBy=isvtest tag."""
    module = _load_security_script("teardown.py")
    iam = FakeIamTags([{"Tags": [{"Key": "CreatedBy", "Value": "isvtest"}], "IsTruncated": False}])

    assert module._user_has_isvtest_tag(iam, "isv-sa-test-1234") is True


def test_teardown_does_not_treat_prefix_only_users_as_owned() -> None:
    """A matching username prefix is not enough to delete a user."""
    module = _load_security_script("teardown.py")
    iam = FakeIamTags([{"Tags": [{"Key": "CreatedBy", "Value": "someone-else"}], "IsTruncated": False}])

    assert module._user_has_isvtest_tag(iam, "isv-sa-test-1234") is False


def test_teardown_checks_paginated_user_tags() -> None:
    """Ownership checks scan paginated IAM user tags."""
    module = _load_security_script("teardown.py")
    iam = FakeIamTags(
        [
            {"Tags": [{"Key": "Name", "Value": "validation"}], "IsTruncated": True, "Marker": "next"},
            {"Tags": [{"Key": "CreatedBy", "Value": "isvtest"}], "IsTruncated": False},
        ]
    )

    assert module._user_has_isvtest_tag(iam, "isv-sa-test-1234") is True


class FakeSaCredentialIam:
    """Fake IAM client for service account credential cleanup tests."""

    def __init__(self, delete_access_key_error: ClientError | None = None) -> None:
        """Configure optional delete_access_key failure."""
        self.delete_access_key_error = delete_access_key_error

    def create_user(self, UserName: str, Tags: list[dict[str, str]]) -> None:
        """Record user creation."""
        assert UserName.startswith("isv-sa-test-")
        assert {"Key": "CreatedBy", "Value": "isvtest"} in Tags

    def create_access_key(self, UserName: str) -> dict[str, dict[str, str]]:
        """Return a fake long-lived access key."""
        assert UserName.startswith("isv-sa-test-")
        return {"AccessKey": {"AccessKeyId": "AKIA_TEST", "SecretAccessKey": "secret"}}

    def delete_access_key(self, UserName: str, AccessKeyId: str) -> None:
        """Optionally fail access key deletion."""
        assert UserName.startswith("isv-sa-test-")
        assert AccessKeyId == "AKIA_TEST"
        if self.delete_access_key_error:
            raise self.delete_access_key_error

    def delete_user(self, UserName: str) -> None:
        """Delete the fake IAM user."""
        assert UserName.startswith("isv-sa-test-")


class FakeSts:
    """Fake STS client for service account credential tests."""

    def get_caller_identity(self) -> dict[str, str]:
        """Return a fake caller identity."""
        return {"Arn": "arn:aws:iam::123456789012:user/isv-sa-test-unit"}


def test_sa_credential_main_fails_when_cleanup_fails(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Successful authentication is reported failed when IAM cleanup fails."""
    module = _load_security_script("sa_credential_test.py")
    iam = FakeSaCredentialIam(delete_access_key_error=_client_error("DeleteAccessKey"))
    sts = FakeSts()

    def fake_client(service_name: str, **kwargs: Any) -> FakeSaCredentialIam | FakeSts:
        """Return fake clients for IAM and STS."""
        if service_name == "iam":
            return iam
        if service_name == "sts":
            return sts
        msg = f"unexpected service: {service_name}"
        raise AssertionError(msg)

    monkeypatch.setattr(module.boto3, "client", fake_client)
    monkeypatch.setattr(module.sys, "argv", ["sa_credential_test.py", "--region", "us-west-2"])

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["success"] is False
    assert payload["authenticated"] is True
    assert "cleanup_errors" in payload
    assert "delete access key AKIA_TEST" in payload["cleanup_errors"][0]


class FakePaginator:
    """Fake paginator for list_users."""

    def paginate(self) -> list[dict[str, list[dict[str, str]]]]:
        """Return one owned test user."""
        return [{"Users": [{"UserName": "isv-sa-test-leftover"}]}]


class FakeTeardownIam:
    """Fake IAM client for teardown cleanup tests."""

    def __init__(self) -> None:
        """Initialize call tracking."""
        self.delete_user_called = False

    def get_paginator(self, operation_name: str) -> FakePaginator:
        """Return a fake list_users paginator."""
        assert operation_name == "list_users"
        return FakePaginator()

    def list_user_tags(self, UserName: str) -> dict[str, Any]:
        """Return ownership tag for the fake user."""
        assert UserName == "isv-sa-test-leftover"
        return {"Tags": [{"Key": "CreatedBy", "Value": "isvtest"}], "IsTruncated": False}

    def list_access_keys(self, UserName: str) -> dict[str, list[dict[str, str]]]:
        """Return one fake access key."""
        assert UserName == "isv-sa-test-leftover"
        return {"AccessKeyMetadata": [{"AccessKeyId": "AKIA_LEFTOVER"}]}

    def delete_access_key(self, UserName: str, AccessKeyId: str) -> None:
        """Fail access key deletion."""
        assert UserName == "isv-sa-test-leftover"
        assert AccessKeyId == "AKIA_LEFTOVER"
        raise _client_error("DeleteAccessKey")

    def delete_user(self, UserName: str) -> None:
        """Fail user deletion after access key deletion failed."""
        assert UserName == "isv-sa-test-leftover"
        self.delete_user_called = True
        raise _client_error("DeleteUser", code="DeleteConflict")


def test_teardown_main_fails_when_owned_user_cleanup_fails(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Teardown reports failure when owned IAM resources cannot be removed."""
    module = _load_security_script("teardown.py")
    iam = FakeTeardownIam()

    def fake_client(service_name: str, **kwargs: Any) -> FakeTeardownIam:
        """Return the fake IAM client."""
        assert service_name == "iam"
        return iam

    monkeypatch.setattr(module.boto3, "client", fake_client)
    monkeypatch.setattr(module.sys, "argv", ["teardown.py", "--region", "us-west-2"])

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["success"] is False
    assert payload["resources_cleaned"] == 0
    assert payload["resources_failed"][0]["username"] == "isv-sa-test-leftover"
    assert len(payload["resources_failed"][0]["errors"]) == 2
    assert iam.delete_user_called is True
