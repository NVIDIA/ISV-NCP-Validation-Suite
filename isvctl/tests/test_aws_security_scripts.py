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
import io
import json
from email.message import Message
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.error import HTTPError

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


class FakeBmcManagementEc2:
    """Fake EC2 client for BMC management-network checks."""

    def __init__(
        self,
        *,
        vpcs: list[dict[str, Any]] | None = None,
        route_tables: list[dict[str, Any]] | None = None,
        network_acls: list[dict[str, Any]] | None = None,
    ) -> None:
        """Initialize paginated EC2 responses."""
        self.paginators = {
            "describe_vpcs": FakeEc2Paginator(
                [
                    {
                        "Vpcs": vpcs
                        if vpcs is not None
                        else [
                            {
                                "VpcId": "vpc-tenant",
                                "CidrBlock": "10.0.0.0/16",
                                "CidrBlockAssociationSet": [{"CidrBlock": "10.0.0.0/16"}],
                            }
                        ]
                    }
                ]
            ),
            "describe_route_tables": FakeEc2Paginator([{"RouteTables": route_tables or []}]),
            "describe_network_acls": FakeEc2Paginator([{"NetworkAcls": network_acls or []}]),
        }

    def get_paginator(self, operation_name: str) -> FakeEc2Paginator:
        """Return a fake paginator for the requested EC2 operation."""
        return self.paginators[operation_name]


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


def test_bmc_management_network_detects_tenant_cidr_overlap() -> None:
    """SEC12-01 fails when tenant VPC CIDRs overlap reserved management ranges."""
    module = _load_security_script("bmc_management_network_test.py")
    vpcs = [
        {
            "VpcId": "vpc-mgmt-overlap",
            "CidrBlock": "198.18.1.0/24",
            "CidrBlockAssociationSet": [{"CidrBlock": "198.18.1.0/24"}],
        }
    ]

    result = module._check_dedicated_management_network(vpcs)

    assert result["passed"] is False
    assert "198.18.1.0/24" in result["error"]


def test_bmc_management_network_detects_management_tag() -> None:
    """SEC12-01 fails when a tenant VPC is tagged as a BMC management network."""
    module = _load_security_script("bmc_management_network_test.py")
    vpcs = [
        {
            "VpcId": "vpc-mgmt-tag",
            "CidrBlock": "10.0.0.0/16",
            "CidrBlockAssociationSet": [{"CidrBlock": "10.0.0.0/16"}],
            "Tags": [{"Key": "Role", "Value": "bmc-network"}],
        }
    ]

    result = module._check_tenant_network_not_management(vpcs)

    assert result["passed"] is False
    assert "vpc-mgmt-tag" in result["error"]


def test_bmc_management_tag_matches_underscore_delimited() -> None:
    """Tag matcher catches underscore-delimited management names like bmc_network."""
    module = _load_security_script("bmc_management_network_test.py")
    vpcs = [
        {
            "VpcId": "vpc-underscore",
            "CidrBlock": "10.0.0.0/16",
            "CidrBlockAssociationSet": [{"CidrBlock": "10.0.0.0/16"}],
            "Tags": [{"Key": "Name", "Value": "bmc_network"}],
        }
    ]

    result = module._check_tenant_network_not_management(vpcs)

    assert result["passed"] is False
    assert "vpc-underscore" in result["error"]


def test_bmc_management_tag_avoids_substring_false_positive() -> None:
    """Tag matcher rejects unrelated identifiers that contain management substrings."""
    module = _load_security_script("bmc_management_network_test.py")
    vpcs = [
        {
            "VpcId": "vpc-tenant",
            "CidrBlock": "10.0.0.0/16",
            "CidrBlockAssociationSet": [{"CidrBlock": "10.0.0.0/16"}],
            "Tags": [{"Key": "Name", "Value": "submarine-bmcollege"}],
        }
    ]

    result = module._check_tenant_network_not_management(vpcs)

    assert result["passed"] is True


def test_bmc_management_network_detects_explicit_management_routes() -> None:
    """SEC12-01 fails when a tenant route table targets part of a management CIDR."""
    module = _load_security_script("bmc_management_network_test.py")
    ec2 = FakeBmcManagementEc2(
        route_tables=[
            {
                "RouteTableId": "rtb-mgmt",
                "Routes": [{"DestinationCidrBlock": "198.18.1.0/24"}],
            }
        ]
    )

    result = module._check_restricted_management_routes(ec2, ["vpc-tenant"])

    assert result["passed"] is False
    assert "rtb-mgmt" in result["error"]


def test_bmc_management_network_detects_management_acl_host_route() -> None:
    """SEC12-01 fails when a NACL explicitly allows a host inside a management range."""
    module = _load_security_script("bmc_management_network_test.py")
    ec2 = FakeBmcManagementEc2(
        network_acls=[
            {
                "NetworkAclId": "acl-mgmt",
                "Entries": [
                    {
                        "RuleAction": "allow",
                        "CidrBlock": "169.254.169.254/32",
                    }
                ],
            }
        ]
    )

    result = module._check_management_acl_enforced(ec2, ["vpc-tenant"])

    assert result["passed"] is False
    assert "acl-mgmt" in result["error"]


def test_bmc_management_network_exempts_default_routes() -> None:
    """SEC12-01 route checks do not treat default internet routes as management routes."""
    module = _load_security_script("bmc_management_network_test.py")
    ec2 = FakeBmcManagementEc2(
        route_tables=[
            {
                "RouteTableId": "rtb-default",
                "Routes": [{"DestinationCidrBlock": "0.0.0.0/0"}],
            }
        ]
    )

    result = module._check_restricted_management_routes(ec2, ["vpc-tenant"])

    assert result["passed"] is True


def test_bmc_management_network_main_emits_sec12_01_contract(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Successful AWS reference run emits the SEC12-01 validation contract."""
    module = _load_security_script("bmc_management_network_test.py")
    ec2 = FakeBmcManagementEc2()

    def fake_client(service_name: str, **kwargs: Any) -> FakeBmcManagementEc2:
        """Return the fake EC2 client."""
        assert service_name == "ec2"
        return ec2

    monkeypatch.setattr(module.boto3, "client", fake_client)
    monkeypatch.setattr(module.sys, "argv", ["bmc_management_network_test.py", "--region", "us-west-2"])

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["success"] is True
    assert payload["test_name"] == "bmc_management_network"
    assert set(payload["tests"]) == {
        "dedicated_management_network",
        "restricted_management_routes",
        "tenant_network_not_management",
        "management_acl_enforced",
    }


def test_bmc_protocol_security_reports_no_customer_bmc_surface() -> None:
    """AWS BMC protocol check emits all CNP10-01 keys for the no-surface case."""
    module = _load_security_script("bmc_protocol_security_test.py")

    result = module._aws_no_customer_bmc_result("us-west-2")

    assert result["success"] is True
    assert result["bmc_endpoints_tested"] == 0
    assert result["bmc_protocol_surface"] == "none"
    assert set(result["tests"]) == {
        "ipmi_disabled",
        "redfish_tls_enabled",
        "redfish_plain_http_disabled",
        "redfish_authentication_required",
        "redfish_authorization_enforced",
        "redfish_accounting_enabled",
    }
    assert all(test["passed"] is True for test in result["tests"].values())
    assert "do not receive customer-accessible IPMI or Redfish" in result["evidence"]


class FakeStsClient:
    """Small fake for STS GetCallerIdentity."""

    def __init__(self, error: Exception | None = None) -> None:
        """Store an optional error returned by get_caller_identity."""
        self.error = error

    def get_caller_identity(self) -> dict[str, str]:
        """Return a fake caller identity or raise the configured error."""
        if self.error:
            raise self.error
        return {"Account": "123456789012", "Arn": "arn:aws:iam::123456789012:user/test", "UserId": "test"}


def _patch_sts_client(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
    sts: FakeStsClient,
    *,
    expected_region: str,
) -> None:
    """Patch boto3.client to return a fake STS client."""

    def fake_client(service_name: str, region_name: str | None = None) -> FakeStsClient:
        """Return the fake STS client for STS requests."""
        assert service_name == "sts"
        assert region_name == expected_region
        return sts

    monkeypatch.setattr(module.boto3, "client", fake_client)


def test_bmc_protocol_security_main_outputs_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AWS BMC protocol script prints the provider-agnostic JSON contract."""
    module = _load_security_script("bmc_protocol_security_test.py")
    monkeypatch.setattr(module.sys, "argv", ["bmc_protocol_security_test.py", "--region", "eu-west-1"])
    _patch_sts_client(monkeypatch, module, FakeStsClient(), expected_region="eu-west-1")

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["success"] is True
    assert payload["region"] == "eu-west-1"
    assert payload["test_name"] == "bmc_protocol_security"
    assert payload["tests"]["ipmi_disabled"]["passed"] is True


def test_bmc_protocol_security_main_reports_sts_probe_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AWS BMC protocol script fails closed when the STS probe fails."""
    module = _load_security_script("bmc_protocol_security_test.py")
    monkeypatch.setattr(module.sys, "argv", ["bmc_protocol_security_test.py", "--region", "eu-west-1"])
    _patch_sts_client(monkeypatch, module, FakeStsClient(RuntimeError("sts unavailable")), expected_region="eu-west-1")

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["success"] is False
    assert payload["platform"] == "security"
    assert payload["test_name"] == "bmc_protocol_security"
    assert payload["region"] == "eu-west-1"
    assert "sts unavailable" in payload["evidence"]
    assert all(test["passed"] is False for test in payload["tests"].values())


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


@pytest.fixture(scope="module")
def oidc_module() -> ModuleType:
    """Load the OIDC user auth script as a module."""
    return _load_security_script("oidc_user_auth_test.py")


class FakeHttpResponse:
    """Small context-manager response for urllib-based OIDC tests."""

    def __init__(self, payload: dict[str, Any] | None = None, status_code: int = 200) -> None:
        """Store response payload and status code."""
        self.payload = payload or {}
        self.status_code = status_code

    def __enter__(self) -> FakeHttpResponse:
        """Enter response context."""
        return self

    def __exit__(self, *_args: Any) -> None:
        """Exit response context."""
        return None

    def read(self) -> bytes:
        """Return JSON response bytes."""
        return json.dumps(self.payload).encode("utf-8")

    def getcode(self) -> int:
        """Return HTTP status code."""
        return self.status_code


def _make_oidc_fixture(oidc_module: ModuleType) -> dict[str, Any]:
    """Build tokens, discovery metadata, and JWKS for OIDC script tests."""
    from cryptography.hazmat.primitives.asymmetric import rsa as _rsa

    issuer = "https://oidc.test.local/realms/isv"
    audience = "isv-validation"
    target_url = "https://platform.test.local/protected"
    private_key = _rsa.generate_private_key(public_exponent=65537, key_size=2048)
    kid = "kid-1"
    jwks = {"keys": [oidc_module._public_jwk(private_key.public_key(), kid)]}
    discovery = {
        "issuer": issuer,
        "jwks_uri": f"{issuer}/protocol/openid-connect/certs",
        "response_types_supported": ["code", "id_token"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
    }
    now = int(oidc_module.time.time())
    base_claims = {
        "iss": issuer,
        "sub": "isv-test-user",
        "aud": audience,
        "iat": now,
        "exp": now + 600,
    }
    return {
        "issuer": issuer,
        "audience": audience,
        "target_url": target_url,
        "discovery": discovery,
        "jwks": jwks,
        "valid_token": oidc_module._sign_jwt(base_claims, private_key, kid),
        "invalid_tokens": {
            "wrong_issuer_rejected": oidc_module._sign_jwt({**base_claims, "iss": f"{issuer}-evil"}, private_key, kid),
            "wrong_audience_rejected": oidc_module._sign_jwt(
                {**base_claims, "aud": "wrong-audience"}, private_key, kid
            ),
            "expired_token_rejected": oidc_module._sign_jwt(
                {**base_claims, "iat": now - 120, "exp": now - 60}, private_key, kid
            ),
            "missing_required_claim_rejected": oidc_module._sign_jwt(
                base_claims, private_key, kid, drop_claims=("sub",)
            ),
        },
    }


def _patch_oidc_urlopen(
    monkeypatch: pytest.MonkeyPatch,
    oidc_module: ModuleType,
    fixture: dict[str, Any],
) -> list[str]:
    """Patch urlopen so OIDC probes exercise fake remote HTTP endpoints."""
    seen_tokens: list[str] = []

    def fake_urlopen(request: Any, timeout: int = 0) -> FakeHttpResponse:
        """Serve discovery/JWKS and enforce target bearer-token behavior."""
        url = request.full_url
        if url == f"{fixture['issuer']}/.well-known/openid-configuration":
            return FakeHttpResponse(fixture["discovery"])
        if url == fixture["discovery"]["jwks_uri"]:
            return FakeHttpResponse(fixture["jwks"])
        if url == fixture["target_url"]:
            auth_header = request.get_header("Authorization", "")
            token = auth_header.removeprefix("Bearer ")
            seen_tokens.append(token)
            if token == fixture["valid_token"]:
                return FakeHttpResponse({}, status_code=200)
            raise HTTPError(url, 401, "Unauthorized", Message(), io.BytesIO(b""))
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(oidc_module, "urlopen", fake_urlopen)
    return seen_tokens


def test_oidc_run_probes_all_pass(oidc_module: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    """All seven OIDC probes pass against configured remote endpoints."""
    fixture = _make_oidc_fixture(oidc_module)
    seen_tokens = _patch_oidc_urlopen(monkeypatch, oidc_module, fixture)

    probes = oidc_module.run_probes(
        fixture["issuer"],
        fixture["audience"],
        fixture["target_url"],
        fixture["valid_token"],
        fixture["invalid_tokens"],
    )

    expected = {
        "valid_token_accepted",
        "bad_signature_rejected",
        "wrong_issuer_rejected",
        "wrong_audience_rejected",
        "expired_token_rejected",
        "missing_required_claim_rejected",
        "discovery_and_jwks_reachable",
    }
    assert set(probes) == expected
    for name, probe in probes.items():
        assert probe["passed"], f"{name} did not pass: {probe}"
    assert len(seen_tokens) == 6


@pytest.mark.parametrize(
    ("jwks", "expected_error"),
    [
        ({"keys": {"kid": "kid-1"}}, "JWKS keys is not a list"),
        ({"keys": []}, "JWKS has no usable RSA keys"),
        ({"keys": ["not-a-key", {"kty": "EC", "kid": "kid-1"}]}, "JWKS has no usable RSA keys"),
        ({"keys": [{"kty": "RSA", "kid": "kid-1"}]}, "JWKS RSA key at index 0 missing required fields: n, e"),
    ],
)
def test_oidc_run_probes_fails_cleanly_for_malformed_jwks(
    oidc_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    jwks: dict[str, Any],
    expected_error: str,
) -> None:
    """Malformed JWKS discovery data fails the discovery probe without raising."""
    fixture = _make_oidc_fixture(oidc_module)
    fixture["jwks"] = jwks
    seen_tokens = _patch_oidc_urlopen(monkeypatch, oidc_module, fixture)

    probes = oidc_module.run_probes(
        fixture["issuer"],
        fixture["audience"],
        fixture["target_url"],
        fixture["valid_token"],
        fixture["invalid_tokens"],
    )

    assert probes["discovery_and_jwks_reachable"]["passed"] is False
    assert probes["discovery_and_jwks_reachable"]["error"] == expected_error
    assert len(seen_tokens) == 0


def test_oidc_run_probes_accepts_jwks_with_non_rsa_entries(
    oidc_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JWKS discovery accepts mixed key sets when at least one RSA key is usable."""
    fixture = _make_oidc_fixture(oidc_module)
    fixture["jwks"]["keys"] = [
        "not-a-key",
        {"kty": "EC", "kid": "kid-1"},
        *fixture["jwks"]["keys"],
    ]
    seen_tokens = _patch_oidc_urlopen(monkeypatch, oidc_module, fixture)

    probes = oidc_module.run_probes(
        fixture["issuer"],
        fixture["audience"],
        fixture["target_url"],
        fixture["valid_token"],
        fixture["invalid_tokens"],
    )

    assert probes["discovery_and_jwks_reachable"]["passed"] is True
    assert all(probe["passed"] for probe in probes.values())
    assert len(seen_tokens) == 6


def test_oidc_run_probes_rejects_malformed_rsa_jwks_even_with_valid_rsa(
    oidc_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed RSA JWKS entries fail discovery even when another RSA key is usable."""
    fixture = _make_oidc_fixture(oidc_module)
    fixture["jwks"]["keys"].append({"kty": "RSA", "kid": "kid-2", "n": "abc"})
    seen_tokens = _patch_oidc_urlopen(monkeypatch, oidc_module, fixture)

    probes = oidc_module.run_probes(
        fixture["issuer"],
        fixture["audience"],
        fixture["target_url"],
        fixture["valid_token"],
        fixture["invalid_tokens"],
    )

    assert probes["discovery_and_jwks_reachable"]["passed"] is False
    assert probes["discovery_and_jwks_reachable"]["error"] == "JWKS RSA key at index 1 missing required fields: e"
    assert len(seen_tokens) == 0


def test_oidc_run_probes_fails_cleanly_for_malformed_discovery_signing_algorithms(
    oidc_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed discovery algorithm metadata fails the discovery probe without raising."""
    fixture = _make_oidc_fixture(oidc_module)
    fixture["discovery"]["id_token_signing_alg_values_supported"] = 123
    seen_tokens = _patch_oidc_urlopen(monkeypatch, oidc_module, fixture)

    probes = oidc_module.run_probes(
        fixture["issuer"],
        fixture["audience"],
        fixture["target_url"],
        fixture["valid_token"],
        fixture["invalid_tokens"],
    )

    assert probes["discovery_and_jwks_reachable"]["passed"] is False
    assert (
        probes["discovery_and_jwks_reachable"]["error"]
        == "discovery id_token_signing_alg_values_supported is not a list"
    )
    assert len(seen_tokens) == 0


def test_oidc_run_probes_rejects_miswired_negative_fixture(
    oidc_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Negative fixtures must match the specific defect they claim to exercise."""
    fixture = _make_oidc_fixture(oidc_module)
    seen_tokens = _patch_oidc_urlopen(monkeypatch, oidc_module, fixture)
    invalid_tokens = dict(fixture["invalid_tokens"])
    invalid_tokens["wrong_audience_rejected"] = fixture["invalid_tokens"]["expired_token_rejected"]

    probes = oidc_module.run_probes(
        fixture["issuer"],
        fixture["audience"],
        fixture["target_url"],
        fixture["valid_token"],
        invalid_tokens,
    )

    assert probes["wrong_audience_rejected"]["passed"] is False
    assert "wrong_audience_rejected fixture invalid" in probes["wrong_audience_rejected"]["error"]
    assert "audience includes the expected audience" in probes["wrong_audience_rejected"]["error"]
    assert len(seen_tokens) == 5


@pytest.mark.parametrize(
    ("claim_overrides", "drop_claims", "expected_error"),
    [
        ({"iss": "https://issuer.example.com/evil"}, ("sub",), "token also has the wrong issuer"),
        ({"aud": "wrong-audience"}, ("sub",), "token also has the wrong audience"),
        ({"exp": 1_699_999_940}, ("sub",), "token is expired instead"),
        ({}, ("sub", "exp"), "missing required claim: exp"),
    ],
)
def test_oidc_missing_claim_fixture_rejects_additional_defects(
    oidc_module: ModuleType,
    claim_overrides: dict[str, Any],
    drop_claims: tuple[str, ...],
    expected_error: str,
) -> None:
    """Missing-claim fixtures fail locally when they also have unrelated defects."""
    from cryptography.hazmat.primitives.asymmetric import rsa as _rsa

    issuer = "https://issuer.example.com"
    audience = "isv-validation"
    now = 1_700_000_000
    private_key = _rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwks = {"keys": [oidc_module._public_jwk(private_key.public_key(), "kid-1")]}
    claims = {
        "iss": issuer,
        "sub": "isv-test-user",
        "aud": audience,
        "iat": now,
        "exp": now + 600,
        **claim_overrides,
    }
    token = oidc_module._sign_jwt(claims, private_key, "kid-1", drop_claims=drop_claims)

    fixture_error = oidc_module._validate_negative_fixture(
        "missing_required_claim_rejected",
        token,
        jwks,
        issuer,
        audience,
        now=now,
    )

    assert fixture_error == expected_error


def test_oidc_run_probes_rejects_malformed_negative_fixture(
    oidc_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed negative fixtures fail locally instead of counting as claim coverage."""
    fixture = _make_oidc_fixture(oidc_module)
    seen_tokens = _patch_oidc_urlopen(monkeypatch, oidc_module, fixture)
    invalid_tokens = dict(fixture["invalid_tokens"])
    invalid_tokens["wrong_issuer_rejected"] = "not-a-jwt"

    probes = oidc_module.run_probes(
        fixture["issuer"],
        fixture["audience"],
        fixture["target_url"],
        fixture["valid_token"],
        invalid_tokens,
    )

    assert probes["wrong_issuer_rejected"]["passed"] is False
    assert "wrong_issuer_rejected fixture invalid: malformed token" in probes["wrong_issuer_rejected"]["error"]
    assert len(seen_tokens) == 5


def test_oidc_run_probes_rejects_bad_signature_negative_fixture(
    oidc_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Claim-specific negative fixtures must be validly signed before endpoint probing."""
    fixture = _make_oidc_fixture(oidc_module)
    seen_tokens = _patch_oidc_urlopen(monkeypatch, oidc_module, fixture)
    invalid_tokens = dict(fixture["invalid_tokens"])
    invalid_tokens["wrong_audience_rejected"] = oidc_module._tamper_signature(
        fixture["invalid_tokens"]["wrong_audience_rejected"]
    )

    probes = oidc_module.run_probes(
        fixture["issuer"],
        fixture["audience"],
        fixture["target_url"],
        fixture["valid_token"],
        invalid_tokens,
    )

    assert probes["wrong_audience_rejected"]["passed"] is False
    assert "wrong_audience_rejected fixture invalid" in probes["wrong_audience_rejected"]["error"]
    assert "token signature invalid: invalid signature" in probes["wrong_audience_rejected"]["error"]
    assert len(seen_tokens) == 5


def test_oidc_run_probes_fails_when_negative_fixture_missing(
    oidc_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing negative fixture still fails the corresponding probe."""
    fixture = _make_oidc_fixture(oidc_module)
    seen_tokens = _patch_oidc_urlopen(monkeypatch, oidc_module, fixture)
    invalid_tokens = dict(fixture["invalid_tokens"])
    invalid_tokens["expired_token_rejected"] = ""

    probes = oidc_module.run_probes(
        fixture["issuer"],
        fixture["audience"],
        fixture["target_url"],
        fixture["valid_token"],
        invalid_tokens,
    )

    assert probes["expired_token_rejected"] == {"passed": False, "error": "Token not configured"}
    assert len(seen_tokens) == 5


def test_oidc_main_emits_success_json(
    oidc_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """main() emits success=True only when real OIDC inputs are configured."""
    fixture = _make_oidc_fixture(oidc_module)
    _patch_oidc_urlopen(monkeypatch, oidc_module, fixture)
    monkeypatch.setenv("OIDC_VALID_TOKEN", fixture["valid_token"])
    monkeypatch.setenv("OIDC_WRONG_ISSUER_TOKEN", fixture["invalid_tokens"]["wrong_issuer_rejected"])
    monkeypatch.setenv("OIDC_WRONG_AUDIENCE_TOKEN", fixture["invalid_tokens"]["wrong_audience_rejected"])
    monkeypatch.setenv("OIDC_EXPIRED_TOKEN", fixture["invalid_tokens"]["expired_token_rejected"])
    monkeypatch.setenv(
        "OIDC_MISSING_REQUIRED_CLAIM_TOKEN",
        fixture["invalid_tokens"]["missing_required_claim_rejected"],
    )
    monkeypatch.setattr(
        oidc_module.sys,
        "argv",
        [
            "oidc_user_auth_test.py",
            "--region",
            "us-west-2",
            "--issuer-url",
            fixture["issuer"],
            "--audience",
            fixture["audience"],
            "--target-url",
            fixture["target_url"],
        ],
    )

    exit_code = oidc_module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["success"] is True
    assert payload["test_name"] == "oidc_user_auth_test"
    assert payload["platform"] == "security"
    assert payload["target_url"] == fixture["target_url"]
    assert len(payload["tests"]) == 7
    assert all(p["passed"] for p in payload["tests"].values())


def test_oidc_main_fails_closed_without_real_configuration(
    oidc_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """main() must not pass with the default unconfigured OIDC settings."""
    for env_var in (
        "OIDC_ISSUER_URL",
        "OIDC_AUDIENCE",
        "OIDC_TARGET_URL",
        "OIDC_VALID_TOKEN",
    ):
        monkeypatch.delenv(env_var, raising=False)
    monkeypatch.setattr(oidc_module.sys, "argv", ["oidc_user_auth_test.py", "--region", "us-west-2"])

    exit_code = oidc_module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["success"] is False
    assert payload["endpoints_tested"] == 0
    assert "OIDC validation not configured" in payload["error"]
    assert all(not probe["passed"] for probe in payload["tests"].values())


def test_oidc_main_fails_closed_with_inline_empty_config_args(
    oidc_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Inline empty args reach the script and produce structured fail-closed JSON."""
    for env_var in (
        "OIDC_ISSUER_URL",
        "OIDC_AUDIENCE",
        "OIDC_TARGET_URL",
        "OIDC_VALID_TOKEN",
    ):
        monkeypatch.delenv(env_var, raising=False)
    monkeypatch.setattr(
        oidc_module.sys,
        "argv",
        [
            "oidc_user_auth_test.py",
            "--region",
            "us-west-2",
            "--issuer-url=",
            "--audience=",
            "--target-url=",
        ],
    )

    exit_code = oidc_module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["success"] is False
    assert payload["endpoints_tested"] == 0
    assert "OIDC validation not configured" in payload["error"]
    assert all(not probe["passed"] for probe in payload["tests"].values())


def test_oidc_main_fails_when_probes_fail(
    oidc_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """main() returns non-zero and success=False when probes regress."""
    failing = {
        name: {"passed": False, "error": "forced"}
        for name in (
            "valid_token_accepted",
            "bad_signature_rejected",
            "wrong_issuer_rejected",
            "wrong_audience_rejected",
            "expired_token_rejected",
            "missing_required_claim_rejected",
            "discovery_and_jwks_reachable",
        )
    }
    fixture = _make_oidc_fixture(oidc_module)
    monkeypatch.setattr(oidc_module, "run_probes", lambda *_a, **_kw: failing)
    monkeypatch.setenv("OIDC_VALID_TOKEN", fixture["valid_token"])
    monkeypatch.setattr(
        oidc_module.sys,
        "argv",
        [
            "oidc_user_auth_test.py",
            "--region",
            "us-west-2",
            "--issuer-url",
            fixture["issuer"],
            "--audience",
            fixture["audience"],
            "--target-url",
            fixture["target_url"],
        ],
    )

    exit_code = oidc_module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["success"] is False


def test_oidc_verify_rejects_alg_none(oidc_module: ModuleType) -> None:
    """Verifier must reject alg!=RS256 even when signature bytes are valid."""
    from cryptography.hazmat.primitives.asymmetric import rsa as _rsa

    private_key = _rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    jwks = {"keys": [oidc_module._public_jwk(public_key, "kid-1")]}

    header = {"alg": "none", "typ": "JWT", "kid": "kid-1"}
    payload = {
        "iss": "iss",
        "sub": "s",
        "aud": "aud",
        "iat": 0,
        "exp": 9999999999,
    }
    b64h = oidc_module._b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    b64p = oidc_module._b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    token = f"{b64h}.{b64p}."

    ok, detail = oidc_module._verify_jwt(token, jwks, "iss", "aud")
    assert not ok
    assert "alg" in detail


def test_oidc_verify_rejects_non_object_jwt_parts(oidc_module: ModuleType) -> None:
    """Verifier must report malformed JWT JSON parts instead of raising AttributeError."""
    valid_header = {"alg": "RS256", "typ": "JWT", "kid": "kid-1"}
    valid_payload = {
        "iss": "iss",
        "sub": "s",
        "aud": "aud",
        "iat": 0,
        "exp": 9999999999,
    }
    non_object_header = oidc_module._b64url_encode(json.dumps(["bad-header"]).encode())
    object_payload = oidc_module._b64url_encode(json.dumps(valid_payload).encode())
    object_header = oidc_module._b64url_encode(json.dumps(valid_header).encode())
    non_object_payload = oidc_module._b64url_encode(json.dumps(["bad-payload"]).encode())

    ok, detail = oidc_module._verify_jwt(f"{non_object_header}.{object_payload}.", {"keys": []}, "iss", "aud")
    assert not ok
    assert "JWT header is not an object: list" in detail

    ok, detail = oidc_module._verify_jwt(f"{object_header}.{non_object_payload}.", {"keys": []}, "iss", "aud")
    assert not ok
    assert "JWT payload is not an object: list" in detail


def test_oidc_verify_normalizes_base64_decode_errors(oidc_module: ModuleType) -> None:
    """Malformed base64url input must surface as verifier decode errors."""
    ok, detail = oidc_module._verify_jwt("a.b.c", {"keys": []}, "iss", "aud")

    assert not ok
    assert "decode error: invalid base64url data:" in detail


def test_oidc_verify_handles_aud_list(oidc_module: ModuleType) -> None:
    """Audience claim may be a list - membership counts as match."""
    from cryptography.hazmat.primitives.asymmetric import rsa as _rsa

    private_key = _rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwks = {"keys": [oidc_module._public_jwk(private_key.public_key(), "kid-1")]}
    now = 1_700_000_000
    claims = {
        "iss": "iss",
        "sub": "s",
        "aud": ["other", "isv-validation"],
        "iat": now,
        "exp": now + 600,
    }
    token = oidc_module._sign_jwt(claims, private_key, "kid-1")

    ok, _ = oidc_module._verify_jwt(token, jwks, "iss", "isv-validation", now=now)
    assert ok
