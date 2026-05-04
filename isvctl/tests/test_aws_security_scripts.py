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
from datetime import UTC
from email.message import Message
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.error import HTTPError

import pytest
from botocore.exceptions import ClientError, WaiterError

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


class FakeBastionEc2:
    """Fake EC2 client for BMC bastion-access checks."""

    def __init__(
        self,
        *,
        security_groups: list[dict[str, Any]] | None = None,
        subnets: list[dict[str, Any]] | None = None,
        route_tables: list[dict[str, Any]] | None = None,
    ) -> None:
        """Initialize paginated EC2 responses."""
        self.paginators = {
            "describe_security_groups": FakeEc2Paginator(
                [{"SecurityGroups": security_groups if security_groups is not None else []}]
            ),
            "describe_subnets": FakeEc2Paginator([{"Subnets": subnets if subnets is not None else []}]),
            "describe_route_tables": FakeEc2Paginator([{"RouteTables": route_tables or []}]),
        }

    def get_paginator(self, operation_name: str) -> FakeEc2Paginator:
        """Return a fake paginator for the requested EC2 operation."""
        return self.paginators[operation_name]


class FakeBastionRouteTablePaginator:
    """Fake route-table paginator that varies responses by route-table association filter."""

    def __init__(
        self,
        *,
        explicit_route_tables: list[dict[str, Any]] | None = None,
        main_route_tables: list[dict[str, Any]] | None = None,
    ) -> None:
        """Store route tables returned for explicit subnet and main associations."""
        self.explicit_route_tables = explicit_route_tables or []
        self.main_route_tables = main_route_tables or []
        self.calls: list[dict[str, Any]] = []

    def paginate(self, **kwargs: Any) -> list[dict[str, Any]]:
        """Return route tables based on the requested association filter."""
        self.calls.append(kwargs)
        filter_names = {filter_config["Name"] for filter_config in kwargs.get("Filters", [])}
        if "association.main" in filter_names:
            return [{"RouteTables": self.main_route_tables}]
        if "association.subnet-id" in filter_names:
            return [{"RouteTables": self.explicit_route_tables}]
        return [{"RouteTables": []}]


class FakeMainRouteBastionEc2:
    """Fake EC2 client for BMC bastion route-table association checks."""

    def __init__(self, paginator: FakeBastionRouteTablePaginator) -> None:
        """Store the route-table paginator."""
        self.route_table_paginator = paginator

    def get_paginator(self, operation_name: str) -> FakeBastionRouteTablePaginator:
        """Return the fake route-table paginator."""
        assert operation_name == "describe_route_tables"
        return self.route_table_paginator


def test_bmc_bastion_access_provider_hidden_when_no_management_resources(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """SEC12-03 passes with provider_hidden markers when no BMC resources are tagged."""
    module = _load_security_script("bmc_bastion_access_test.py")
    ec2 = FakeBastionEc2()

    def fake_client(service_name: str, **_: Any) -> FakeBastionEc2:
        """Return the fake EC2 client."""
        assert service_name == "ec2"
        return ec2

    monkeypatch.setattr(module.boto3, "client", fake_client)
    monkeypatch.setattr(module.sys, "argv", ["bmc_bastion_access_test.py", "--region", "us-west-2"])

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["success"] is True
    assert payload["test_name"] == "bmc_bastion_access"
    for subtest in (
        "bastion_identifiable",
        "management_ingress_via_bastion_only",
        "no_direct_public_route",
        "bastion_hardened",
    ):
        assert payload["tests"][subtest]["passed"] is True
        assert payload["tests"][subtest]["provider_hidden"] is True


def test_bmc_bastion_access_fails_when_bmc_tagged_but_no_bastion(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When a BMC-tagged resource exists but no bastion is tagged, bastion_identifiable fails."""
    module = _load_security_script("bmc_bastion_access_test.py")
    ec2 = FakeBastionEc2(
        security_groups=[
            {
                "GroupId": "sg-bmc",
                "Tags": [{"Key": "Role", "Value": "bmc-network"}],
                "IpPermissions": [],
            },
        ],
    )

    def fake_client(service_name: str, **_: Any) -> FakeBastionEc2:
        """Return the fake EC2 client."""
        assert service_name == "ec2"
        return ec2

    monkeypatch.setattr(module.boto3, "client", fake_client)
    monkeypatch.setattr(module.sys, "argv", ["bmc_bastion_access_test.py", "--region", "us-west-2"])

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["success"] is False
    assert payload["tests"]["bastion_identifiable"]["passed"] is False
    assert payload["tests"]["bastion_hardened"]["passed"] is False


def test_bmc_bastion_access_detects_world_open_management_ingress() -> None:
    """SEC12-03 fails when a BMC-tagged SG accepts ingress from 0.0.0.0/0 on a management port."""
    module = _load_security_script("bmc_bastion_access_test.py")
    management_sgs = [
        {
            "GroupId": "sg-bmc",
            "Tags": [{"Key": "Role", "Value": "bmc-network"}],
            "IpPermissions": [
                {
                    "IpProtocol": "tcp",
                    "FromPort": 22,
                    "ToPort": 22,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                }
            ],
        }
    ]
    bastion_sgs = [
        {
            "GroupId": "sg-bastion",
            "Tags": [{"Key": "Role", "Value": "bastion"}],
            "IpPermissions": [],
        }
    ]
    bastion_ids = {sg["GroupId"] for sg in bastion_sgs}

    result = module._check_management_ingress_via_bastion_only(management_sgs, bastion_ids)

    assert result["passed"] is False
    assert "sg-bmc" in result["error"]
    assert "public CIDR" in result["error"]


def test_bmc_bastion_access_accepts_bastion_sg_referenced_ingress() -> None:
    """Ingress from the bastion SG (UserIdGroupPairs) is acceptable."""
    module = _load_security_script("bmc_bastion_access_test.py")
    management_sgs = [
        {
            "GroupId": "sg-bmc",
            "Tags": [{"Key": "Role", "Value": "bmc-network"}],
            "IpPermissions": [
                {
                    "IpProtocol": "tcp",
                    "FromPort": 22,
                    "ToPort": 22,
                    "UserIdGroupPairs": [{"GroupId": "sg-bastion"}],
                }
            ],
        }
    ]
    bastion_ids = {"sg-bastion"}

    result = module._check_management_ingress_via_bastion_only(management_sgs, bastion_ids)

    assert result["passed"] is True


def test_bmc_bastion_access_rejects_explicit_cidr_ingress() -> None:
    """Even a non-public CIDR on a management SG fails; ingress must come via bastion SG ref."""
    module = _load_security_script("bmc_bastion_access_test.py")
    management_sgs = [
        {
            "GroupId": "sg-bmc",
            "Tags": [{"Key": "Role", "Value": "bmc-network"}],
            "IpPermissions": [
                {
                    "IpProtocol": "tcp",
                    "FromPort": 22,
                    "ToPort": 22,
                    "IpRanges": [{"CidrIp": "10.99.0.0/24"}],
                }
            ],
        }
    ]

    result = module._check_management_ingress_via_bastion_only(management_sgs, set())

    assert result["passed"] is False
    assert "explicit_cidr=True" in result["error"]


def test_bmc_bastion_access_rejects_prefix_list_ingress() -> None:
    """Prefix-list ingress is not bastion SG ingress and must fail SEC12-03."""
    module = _load_security_script("bmc_bastion_access_test.py")
    management_sgs = [
        {
            "GroupId": "sg-bmc",
            "Tags": [{"Key": "Role", "Value": "bmc-network"}],
            "IpPermissions": [
                {
                    "IpProtocol": "tcp",
                    "FromPort": 22,
                    "ToPort": 22,
                    "PrefixListIds": [{"PrefixListId": "pl-corporate"}],
                }
            ],
        }
    ]

    result = module._check_management_ingress_via_bastion_only(management_sgs, {"sg-bastion"})

    assert result["passed"] is False
    assert "prefix_list=True" in result["error"]


def test_bmc_bastion_access_detects_igw_route_from_management_subnet() -> None:
    """SEC12-03 fails when a BMC-tagged subnet has a 0.0.0.0/0 -> igw route."""
    module = _load_security_script("bmc_bastion_access_test.py")
    management_subnets = [
        {
            "SubnetId": "subnet-bmc",
            "MapPublicIpOnLaunch": False,
            "Tags": [{"Key": "Role", "Value": "bmc-management"}],
        }
    ]
    ec2 = FakeBastionEc2(
        route_tables=[
            {
                "RouteTableId": "rtb-bmc",
                "Routes": [{"DestinationCidrBlock": "0.0.0.0/0", "GatewayId": "igw-12345"}],
            }
        ]
    )

    result = module._check_no_direct_public_route(ec2, management_subnets)

    assert result["passed"] is False
    assert "rtb-bmc" in result["error"]


def test_bmc_bastion_access_detects_igw_route_from_main_route_table() -> None:
    """SEC12-03 checks the VPC main route table when a BMC subnet has no explicit association."""
    module = _load_security_script("bmc_bastion_access_test.py")
    management_subnets = [
        {
            "SubnetId": "subnet-bmc",
            "VpcId": "vpc-bmc",
            "MapPublicIpOnLaunch": False,
            "Tags": [{"Key": "Role", "Value": "bmc-management"}],
        }
    ]
    paginator = FakeBastionRouteTablePaginator(
        main_route_tables=[
            {
                "RouteTableId": "rtb-main-public",
                "Associations": [{"Main": True, "RouteTableAssociationId": "rtbassoc-main"}],
                "Routes": [{"DestinationCidrBlock": "0.0.0.0/0", "GatewayId": "igw-12345"}],
            }
        ]
    )
    ec2 = FakeMainRouteBastionEc2(paginator)

    result = module._check_no_direct_public_route(ec2, management_subnets)

    assert result["passed"] is False
    assert "rtb-main-public" in result["error"]
    assert paginator.calls == [
        {"Filters": [{"Name": "association.subnet-id", "Values": ["subnet-bmc"]}]},
        {
            "Filters": [
                {"Name": "vpc-id", "Values": ["vpc-bmc"]},
                {"Name": "association.main", "Values": ["true"]},
            ]
        },
    ]


def test_bmc_bastion_access_detects_map_public_ip() -> None:
    """SEC12-03 fails when a BMC-tagged subnet auto-assigns public IPs."""
    module = _load_security_script("bmc_bastion_access_test.py")
    management_subnets = [
        {
            "SubnetId": "subnet-bmc",
            "MapPublicIpOnLaunch": True,
            "Tags": [{"Key": "Role", "Value": "bmc-management"}],
        }
    ]
    ec2 = FakeBastionEc2()

    result = module._check_no_direct_public_route(ec2, management_subnets)

    assert result["passed"] is False
    assert "MapPublicIpOnLaunch" in result["error"]


def test_bmc_bastion_access_detects_world_open_bastion_ssh() -> None:
    """SEC12-03 fails when the bastion SG itself allows SSH from 0.0.0.0/0."""
    module = _load_security_script("bmc_bastion_access_test.py")
    bastion_sgs = [
        {
            "GroupId": "sg-bastion",
            "Tags": [{"Key": "Role", "Value": "bastion"}],
            "IpPermissions": [
                {
                    "IpProtocol": "tcp",
                    "FromPort": 22,
                    "ToPort": 22,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                }
            ],
        }
    ]

    result = module._check_bastion_hardened(bastion_sgs)

    assert result["passed"] is False
    assert "sg-bastion" in result["error"]


def test_bmc_bastion_access_main_emits_sec12_03_contract(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Successful AWS reference run emits the SEC12-03 validation contract."""
    module = _load_security_script("bmc_bastion_access_test.py")
    bastion_sg = {
        "GroupId": "sg-bastion",
        "Tags": [{"Key": "Role", "Value": "jumphost"}],
        "IpPermissions": [
            {
                "IpProtocol": "tcp",
                "FromPort": 22,
                "ToPort": 22,
                "IpRanges": [{"CidrIp": "10.0.0.0/16"}],
            }
        ],
    }
    bmc_sg = {
        "GroupId": "sg-bmc",
        "Tags": [{"Key": "Role", "Value": "bmc-network"}],
        "IpPermissions": [
            {
                "IpProtocol": "tcp",
                "FromPort": 22,
                "ToPort": 22,
                "UserIdGroupPairs": [{"GroupId": "sg-bastion"}],
            }
        ],
    }
    bmc_subnet = {
        "SubnetId": "subnet-bmc",
        "MapPublicIpOnLaunch": False,
        "Tags": [{"Key": "Role", "Value": "bmc-management"}],
    }
    ec2 = FakeBastionEc2(
        security_groups=[bastion_sg, bmc_sg],
        subnets=[bmc_subnet],
        route_tables=[{"RouteTableId": "rtb-bmc-private", "Routes": []}],
    )

    def fake_client(service_name: str, **_: Any) -> FakeBastionEc2:
        """Return the fake EC2 client."""
        assert service_name == "ec2"
        return ec2

    monkeypatch.setattr(module.boto3, "client", fake_client)
    monkeypatch.setattr(module.sys, "argv", ["bmc_bastion_access_test.py", "--region", "us-west-2"])

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["success"] is True
    assert payload["test_name"] == "bmc_bastion_access"
    assert set(payload["tests"]) == {
        "bastion_identifiable",
        "management_ingress_via_bastion_only",
        "no_direct_public_route",
        "bastion_hardened",
    }
    for subtest in payload["tests"].values():
        assert subtest["passed"] is True


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

    def list_user_policies(self, UserName: str) -> dict[str, list[str]]:
        """Return no inline policies for the legacy sa_credential test user."""
        assert UserName == "isv-sa-test-leftover"
        return {"PolicyNames": []}

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
    # Two failure paths now plus a list_inline_policies success: keep
    # the existing two-failure assertion but allow the inline-policy
    # listing call to succeed silently.
    assert len(payload["resources_failed"][0]["errors"]) == 2
    assert iam.delete_user_called is True


class FakeSec02CleanupIam:
    """Fake IAM client exercising teardown's inline-policy cleanup path for SEC02 users."""

    def __init__(self) -> None:
        """Initialize call tracking."""
        self.deleted_keys: list[tuple[str, str]] = []
        self.deleted_policies: list[tuple[str, str]] = []
        self.deleted_users: list[str] = []
        # Ordered call log so tests can lock in the relative order of
        # delete_user_policy vs delete_user (the inline policy must be
        # detached first or DeleteUser fails with DeleteConflict on AWS).
        self.call_sequence: list[str] = []

    def list_access_keys(self, UserName: str) -> dict[str, list[dict[str, str]]]:
        """Return one fake access key."""
        assert UserName.startswith("isv-sec02-test-")
        self.call_sequence.append(f"list_access_keys:{UserName}")
        return {"AccessKeyMetadata": [{"AccessKeyId": "AKIA_SEC02"}]}

    def delete_access_key(self, UserName: str, AccessKeyId: str) -> None:
        """Record access key deletion."""
        self.deleted_keys.append((UserName, AccessKeyId))
        self.call_sequence.append(f"delete_access_key:{UserName}:{AccessKeyId}")

    def list_user_policies(self, UserName: str) -> dict[str, list[str]]:
        """Return one inline policy attached to the SEC02 user."""
        assert UserName.startswith("isv-sec02-test-")
        self.call_sequence.append(f"list_user_policies:{UserName}")
        return {"PolicyNames": ["isv-sec02-sts-allow"]}

    def delete_user_policy(self, UserName: str, PolicyName: str) -> None:
        """Record inline policy deletion."""
        self.deleted_policies.append((UserName, PolicyName))
        self.call_sequence.append(f"delete_user_policy:{UserName}:{PolicyName}")

    def delete_user(self, UserName: str) -> None:
        """Record user deletion."""
        self.deleted_users.append(UserName)
        self.call_sequence.append(f"delete_user:{UserName}")


def test_teardown_cleanup_owned_user_deletes_inline_policy_for_sec02_users() -> None:
    """`_cleanup_owned_user` must detach inline policies before deleting SEC02 users."""
    module = _load_security_script("teardown.py")
    iam = FakeSec02CleanupIam()

    cleanup_errors = module._cleanup_owned_user(iam, "isv-sec02-test-abcd1234")

    assert cleanup_errors == []
    assert iam.deleted_keys == [("isv-sec02-test-abcd1234", "AKIA_SEC02")]
    assert iam.deleted_policies == [("isv-sec02-test-abcd1234", "isv-sec02-sts-allow")]
    assert iam.deleted_users == ["isv-sec02-test-abcd1234"]
    # Order matters: AWS DeleteUser fails with DeleteConflict if an inline
    # policy is still attached. Lock in policy-before-user.
    policy_idx = iam.call_sequence.index("delete_user_policy:isv-sec02-test-abcd1234:isv-sec02-sts-allow")
    user_idx = iam.call_sequence.index("delete_user:isv-sec02-test-abcd1234")
    assert policy_idx < user_idx


def test_teardown_owned_user_prefixes_cover_security_test_scripts() -> None:
    """The teardown sweep must recognize both sa_credential and short-lived test users."""
    module = _load_security_script("teardown.py")

    assert "isv-sa-test-".startswith("isv-sa-test-")
    assert "isv-sec02-test-foo".startswith(module.OWNED_USER_PREFIXES)
    assert "isv-sa-test-bar".startswith(module.OWNED_USER_PREFIXES)
    assert not "isv-network-test-baz".startswith(module.OWNED_USER_PREFIXES)


@pytest.fixture(scope="module")
def byok_module() -> ModuleType:
    """Load the customer-managed key script as a module."""
    return _load_security_script("customer_managed_key_test.py")


class FakeByokWaiter:
    """Fake EC2 waiter for encrypted volume tests."""

    def __init__(self, error: Exception | None = None) -> None:
        """Initialize wait call tracking."""
        self.calls: list[dict[str, Any]] = []
        self.error = error

    def wait(self, **kwargs: Any) -> None:
        """Record waiter arguments."""
        self.calls.append(kwargs)
        if self.error:
            raise self.error


class FakeByokKms:
    """Fake KMS client for customer-managed key tests."""

    def __init__(
        self,
        *,
        key_manager: str = "CUSTOMER",
        plaintext_mismatch: bool = False,
        encrypt_error: ClientError | None = None,
    ) -> None:
        """Initialize fake KMS behavior."""
        self.key_metadata = {
            "KeyId": "cmk-123",
            "Arn": "arn:aws:kms:us-west-2:123456789012:key/cmk-123",
            "KeyManager": key_manager,
            "KeyState": "Enabled",
            "KeyUsage": "ENCRYPT_DECRYPT",
        }
        self.plaintext_mismatch = plaintext_mismatch
        self.encrypt_error = encrypt_error
        self.created_keys: list[dict[str, Any]] = []
        self.scheduled_deletions: list[dict[str, Any]] = []

    def create_key(self, **kwargs: Any) -> dict[str, dict[str, Any]]:
        """Create a fake customer-managed key."""
        self.created_keys.append(kwargs)
        return {"KeyMetadata": self.key_metadata}

    def describe_key(self, KeyId: str) -> dict[str, dict[str, Any]]:
        """Return fake KMS key metadata."""
        assert KeyId in {"cmk-123", self.key_metadata["Arn"], "alias/aws/ebs"}
        return {"KeyMetadata": self.key_metadata}

    def encrypt(self, KeyId: str, Plaintext: bytes) -> dict[str, bytes]:
        """Return fake ciphertext or raise the configured error."""
        assert KeyId == "cmk-123"
        if self.encrypt_error:
            raise self.encrypt_error
        return {"CiphertextBlob": b"ciphertext:" + Plaintext}

    def decrypt(self, KeyId: str, CiphertextBlob: bytes) -> dict[str, bytes]:
        """Return the decrypted fake plaintext."""
        assert KeyId == "cmk-123"
        assert CiphertextBlob.startswith(b"ciphertext:")
        if self.plaintext_mismatch:
            return {"Plaintext": b"wrong"}
        return {"Plaintext": CiphertextBlob.removeprefix(b"ciphertext:")}

    def schedule_key_deletion(self, **kwargs: Any) -> None:
        """Record a scheduled key deletion request."""
        self.scheduled_deletions.append(kwargs)


class FakeByokEc2:
    """Fake EC2 client for encrypted EBS volume tests."""

    def __init__(
        self,
        *,
        kms_key_id: str | None = None,
        encrypted: bool = True,
        waiter_error: Exception | None = None,
        describe_error: Exception | None = None,
    ) -> None:
        """Initialize fake EC2 behavior."""
        self.kms_key_id = kms_key_id or "arn:aws:kms:us-west-2:123456789012:key/cmk-123"
        self.encrypted = encrypted
        self.describe_error = describe_error
        self.created_volumes: list[dict[str, Any]] = []
        self.deleted_volumes: list[str] = []
        self.waiter = FakeByokWaiter(waiter_error)

    def describe_availability_zones(self, **kwargs: Any) -> dict[str, list[dict[str, str]]]:
        """Return one available AZ."""
        assert kwargs == {"Filters": [{"Name": "state", "Values": ["available"]}]}
        return {"AvailabilityZones": [{"ZoneName": "us-west-2a", "OptInStatus": "opt-in-not-required"}]}

    def create_volume(self, **kwargs: Any) -> dict[str, Any]:
        """Create a fake encrypted volume."""
        self.created_volumes.append(kwargs)
        return {
            "VolumeId": "vol-byok-123",
            "Encrypted": self.encrypted,
            "KmsKeyId": self.kms_key_id,
        }

    def get_waiter(self, waiter_name: str) -> FakeByokWaiter:
        """Return a fake waiter."""
        assert waiter_name == "volume_available"
        return self.waiter

    def describe_volumes(self, VolumeIds: list[str]) -> dict[str, list[dict[str, Any]]]:
        """Return the fake volume description."""
        assert VolumeIds == ["vol-byok-123"]
        if self.describe_error:
            raise self.describe_error
        return {
            "Volumes": [
                {
                    "VolumeId": "vol-byok-123",
                    "Encrypted": self.encrypted,
                    "KmsKeyId": self.kms_key_id,
                }
            ]
        }

    def delete_volume(self, VolumeId: str) -> None:
        """Record fake volume deletion."""
        self.deleted_volumes.append(VolumeId)


def test_byok_existing_customer_managed_key_path(byok_module: ModuleType) -> None:
    """Existing customer-managed KMS key path passes all SEC09-04 probes."""
    kms = FakeByokKms()
    ec2 = FakeByokEc2()

    result = byok_module._run_customer_managed_key_test(kms, ec2, "us-west-2", "cmk-123")

    assert result["success"] is True
    assert result["key_id"] == "cmk-123"
    assert result["encrypted_resource_id"] == "vol-byok-123"
    assert all(test["passed"] for test in result["tests"].values())
    assert ec2.deleted_volumes == ["vol-byok-123"]
    assert kms.scheduled_deletions == []


def test_byok_rejects_aws_managed_key(byok_module: ModuleType) -> None:
    """AWS-managed KMS keys fail the customer-managed-key contract."""
    kms = FakeByokKms(key_manager="AWS")
    ec2 = FakeByokEc2()

    result = byok_module._run_customer_managed_key_test(kms, ec2, "us-west-2", "alias/aws/ebs")

    assert result["success"] is False
    assert result["tests"]["customer_managed_key_available"]["passed"] is True
    assert result["tests"]["key_manager_is_customer"]["passed"] is False
    assert result["tests"]["provider_managed_key_not_used"]["passed"] is False
    assert ec2.created_volumes == []


def test_byok_encrypt_decrypt_roundtrip_success_and_failure(byok_module: ModuleType) -> None:
    """KMS encrypt/decrypt roundtrip reports success and plaintext mismatch failure."""
    success = byok_module._check_encrypt_decrypt_roundtrip(FakeByokKms(), "cmk-123")
    mismatch = byok_module._check_encrypt_decrypt_roundtrip(FakeByokKms(plaintext_mismatch=True), "cmk-123")
    aws_error = byok_module._check_encrypt_decrypt_roundtrip(
        FakeByokKms(encrypt_error=_client_error("Encrypt")),
        "cmk-123",
    )

    assert success["passed"] is True
    assert mismatch["passed"] is False
    assert "did not match" in mismatch["error"]
    assert aws_error["passed"] is False
    assert "denied" in aws_error["error"]


def test_byok_ebs_volume_kms_key_verification(byok_module: ModuleType) -> None:
    """Encrypted EBS volume verification checks the reported KmsKeyId."""
    key_metadata = FakeByokKms().key_metadata

    success = byok_module._check_resource_encrypted_with_customer_key(FakeByokEc2(), key_metadata, "us-west-2a")
    mismatch = byok_module._check_resource_encrypted_with_customer_key(
        FakeByokEc2(kms_key_id="arn:aws:kms:us-west-2:123456789012:key/other"),
        key_metadata,
        "us-west-2a",
    )

    assert success["passed"] is True
    assert success["volume_id"] == "vol-byok-123"
    assert mismatch["passed"] is False
    assert "unexpected KMS key" in mismatch["error"]


def test_byok_deletes_volume_when_ebs_waiter_fails(byok_module: ModuleType) -> None:
    """EBS waiter failures preserve the volume id so final cleanup can delete it."""
    waiter_error = WaiterError(
        name="VolumeAvailable",
        reason="Max attempts exceeded",
        last_response={"Volumes": [{"VolumeId": "vol-byok-123", "State": "creating"}]},
    )
    kms = FakeByokKms()
    ec2 = FakeByokEc2(waiter_error=waiter_error)

    result = byok_module._run_customer_managed_key_test(kms, ec2, "us-west-2", "cmk-123")

    assert result["success"] is False
    assert result["encrypted_resource_id"] == "vol-byok-123"
    assert result["tests"]["resource_encrypted_with_customer_key"]["passed"] is False
    assert result["tests"]["resource_encrypted_with_customer_key"]["volume_id"] == "vol-byok-123"
    assert ec2.deleted_volumes == ["vol-byok-123"]


def test_byok_deletes_volume_when_ebs_verification_raises_unexpected_error(byok_module: ModuleType) -> None:
    """Unexpected EBS verification errors preserve the volume id for cleanup."""
    kms = FakeByokKms()
    ec2 = FakeByokEc2(describe_error=RuntimeError("describe failed"))

    result = byok_module._run_customer_managed_key_test(kms, ec2, "us-west-2", "cmk-123")

    assert result["success"] is False
    assert result["encrypted_resource_id"] == "vol-byok-123"
    assert result["tests"]["resource_encrypted_with_customer_key"]["volume_id"] == "vol-byok-123"
    assert "describe failed" in result["tests"]["resource_encrypted_with_customer_key"]["error"]
    assert ec2.deleted_volumes == ["vol-byok-123"]


def test_byok_owned_temporary_key_and_volume_are_cleaned_up(byok_module: ModuleType) -> None:
    """Temporary KMS keys are scheduled for deletion and test volumes are deleted."""
    kms = FakeByokKms()
    ec2 = FakeByokEc2()

    result = byok_module._run_customer_managed_key_test(kms, ec2, "us-west-2")

    assert result["success"] is True
    assert kms.created_keys
    assert kms.scheduled_deletions == [{"KeyId": "cmk-123", "PendingWindowInDays": 7}]
    assert ec2.deleted_volumes == ["vol-byok-123"]


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


def test_oidc_main_emits_skip_when_unconfigured(
    oidc_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """main() emits a structured skip (exit 0) when no OIDC inputs are provided."""
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

    assert exit_code == 0
    assert payload["success"] is True
    assert payload["skipped"] is True
    assert payload["endpoints_tested"] == 0
    assert "OIDC validation not configured" in payload["skip_reason"]
    assert payload["tests"] == {}
    assert "error" not in payload


def test_oidc_main_emits_skip_with_inline_empty_config_args(
    oidc_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Inline empty args still produce a structured skip rather than a failure."""
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

    assert exit_code == 0
    assert payload["success"] is True
    assert payload["skipped"] is True
    assert payload["endpoints_tested"] == 0
    assert "OIDC validation not configured" in payload["skip_reason"]
    assert payload["tests"] == {}


def test_oidc_main_skip_resets_endpoints_tested_when_only_target_url_set(
    oidc_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A partially-configured run still reports endpoints_tested=0 on skip."""
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
            "--target-url",
            "https://api.example/protected",
        ],
    )

    exit_code = oidc_module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["skipped"] is True
    assert payload["target_url"] == "https://api.example/protected"
    assert payload["endpoints_tested"] == 0


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


# ===========================================================================
# Short-lived credentials (SEC02-01) tests
# ===========================================================================


@pytest.fixture(scope="module")
def short_lived_module() -> ModuleType:
    """Load the short-lived credentials script as a module."""
    return _load_security_script("short_lived_credentials_test.py")


class FakeShortLivedIam:
    """Fake IAM client tracking SEC02 user provisioning + cleanup calls."""

    def __init__(
        self,
        *,
        create_user_error: ClientError | None = None,
        put_user_policy_error: ClientError | None = None,
        create_access_key_error: ClientError | None = None,
        delete_user_policy_error: ClientError | None = None,
        delete_access_key_error: ClientError | None = None,
        delete_user_error: ClientError | None = None,
    ) -> None:
        """Configure optional per-call failures."""
        self.create_user_error = create_user_error
        self.put_user_policy_error = put_user_policy_error
        self.create_access_key_error = create_access_key_error
        self.delete_user_policy_error = delete_user_policy_error
        self.delete_access_key_error = delete_access_key_error
        self.delete_user_error = delete_user_error
        self.created_users: list[dict[str, Any]] = []
        self.put_policies: list[dict[str, str]] = []
        self.deleted_policies: list[tuple[str, str]] = []
        self.deleted_keys: list[tuple[str, str]] = []
        self.deleted_users: list[str] = []

    def create_user(self, UserName: str, Tags: list[dict[str, str]]) -> dict[str, dict[str, str]]:
        """Create a fake IAM user, recording the call."""
        if self.create_user_error is not None:
            raise self.create_user_error
        assert UserName.startswith("isv-sec02-test-")
        assert {"Key": "CreatedBy", "Value": "isvtest"} in Tags
        self.created_users.append({"UserName": UserName, "Tags": Tags})
        return {"User": {"UserName": UserName, "Arn": f"arn:aws:iam::123:user/{UserName}"}}

    def put_user_policy(self, UserName: str, PolicyName: str, PolicyDocument: str) -> None:
        """Attach a fake inline policy to the test user."""
        if self.put_user_policy_error is not None:
            raise self.put_user_policy_error
        assert UserName.startswith("isv-sec02-test-")
        self.put_policies.append({"UserName": UserName, "PolicyName": PolicyName, "PolicyDocument": PolicyDocument})

    def create_access_key(self, UserName: str) -> dict[str, dict[str, str]]:
        """Return fake access key material for the test user."""
        if self.create_access_key_error is not None:
            raise self.create_access_key_error
        assert UserName.startswith("isv-sec02-test-")
        return {"AccessKey": {"AccessKeyId": "AKIA_FAKE", "SecretAccessKey": "secret_fake"}}

    def delete_user_policy(self, UserName: str, PolicyName: str) -> None:
        """Detach the inline policy, recording the call."""
        if self.delete_user_policy_error is not None:
            raise self.delete_user_policy_error
        self.deleted_policies.append((UserName, PolicyName))

    def delete_access_key(self, UserName: str, AccessKeyId: str) -> None:
        """Delete the test user's access key, recording the call."""
        if self.delete_access_key_error is not None:
            raise self.delete_access_key_error
        self.deleted_keys.append((UserName, AccessKeyId))

    def delete_user(self, UserName: str) -> None:
        """Delete the test user, recording the call."""
        if self.delete_user_error is not None:
            raise self.delete_user_error
        self.deleted_users.append(UserName)


class FakeShortLivedSts:
    """Fake STS client supporting GetSessionToken / GetFederationToken with optional retry sequencing."""

    def __init__(
        self,
        *,
        session_expiration: Any = None,
        session_errors: list[ClientError] | None = None,
        federation_expiration: Any = None,
        federation_error: ClientError | None = None,
        omit_session_expiration: bool = False,
    ) -> None:
        """Configure fake STS responses, optional retry-error sequence on session, and per-probe expirations."""
        self.session_expiration = session_expiration
        self.session_errors: list[ClientError] = list(session_errors) if session_errors else []
        self.federation_expiration = federation_expiration
        self.federation_error = federation_error
        self.omit_session_expiration = omit_session_expiration
        self.federation_calls: list[dict[str, str]] = []
        self.session_call_count = 0

    def get_session_token(self) -> dict[str, dict[str, Any]]:
        """Return fake GetSessionToken response, popping a queued error on each call."""
        self.session_call_count += 1
        if self.session_errors:
            raise self.session_errors.pop(0)
        creds: dict[str, Any] = {
            "AccessKeyId": "ASIA_FAKE",
            "SecretAccessKey": "secret",
            "SessionToken": "session",
        }
        if not self.omit_session_expiration:
            creds["Expiration"] = self.session_expiration
        return {"Credentials": creds}

    def get_federation_token(self, **kwargs: Any) -> dict[str, dict[str, Any]]:
        """Return fake GetFederationToken response or raise the configured error."""
        self.federation_calls.append(kwargs)
        if self.federation_error is not None:
            raise self.federation_error
        return {
            "Credentials": {
                "AccessKeyId": "ASIA_FED_FAKE",
                "SecretAccessKey": "secret",
                "SessionToken": "session",
                "Expiration": self.federation_expiration,
            },
        }


def _patch_short_lived_clients(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
    *,
    iam: FakeShortLivedIam,
    sts: FakeShortLivedSts,
) -> None:
    """Patch boto3.client to return fakes for iam and sts, and zero out the IAM-propagation sleep."""

    def fake_client(service_name: str, **kwargs: Any) -> FakeShortLivedIam | FakeShortLivedSts:
        """Return the matching fake client for iam/sts."""
        if service_name == "iam":
            return iam
        if service_name == "sts":
            return sts
        msg = f"unexpected service: {service_name}"
        raise AssertionError(msg)

    monkeypatch.setattr(module.boto3, "client", fake_client)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)


def _set_short_lived_argv(monkeypatch: pytest.MonkeyPatch, module: ModuleType, *extra_args: str) -> None:
    """Set sys.argv for the short-lived credentials script with optional extra args."""
    monkeypatch.setattr(
        module.sys,
        "argv",
        ["short_lived_credentials_test.py", "--region", "us-west-2", *extra_args],
    )


def test_short_lived_credentials_main_passes_with_bounded_ttls(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    short_lived_module: ModuleType,
) -> None:
    """Both probes pass when STS returns bounded TTLs, and the test user is cleaned up."""
    from datetime import datetime, timedelta

    now = datetime.now(UTC)
    iam = FakeShortLivedIam()
    sts = FakeShortLivedSts(
        session_expiration=now + timedelta(seconds=3600),
        federation_expiration=now + timedelta(seconds=3600),
    )
    _patch_short_lived_clients(monkeypatch, short_lived_module, iam=iam, sts=sts)
    _set_short_lived_argv(monkeypatch, short_lived_module)

    exit_code = short_lived_module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["success"] is True
    assert payload["max_ttl_seconds"] == 43200
    assert payload["node_credential_method"] == "sts:GetSessionToken"
    assert payload["workload_credential_method"] == "sts:GetFederationToken"
    assert 0 < payload["node_credential_ttl_seconds"] <= 3600
    assert 0 < payload["workload_credential_ttl_seconds"] <= 3600
    for probe in payload["tests"].values():
        assert probe["passed"] is True

    assert len(iam.created_users) == 1
    username = iam.created_users[0]["UserName"]
    assert iam.put_policies == [
        {
            "UserName": username,
            "PolicyName": short_lived_module.INLINE_POLICY_NAME,
            "PolicyDocument": short_lived_module.INLINE_STS_POLICY,
        }
    ]
    assert iam.deleted_policies == [(username, short_lived_module.INLINE_POLICY_NAME)]
    assert iam.deleted_keys == [(username, "AKIA_FAKE")]
    assert iam.deleted_users == [username]
    assert len(sts.federation_calls) == 1
    federation_name = sts.federation_calls[0]["Name"]
    assert federation_name.startswith(short_lived_module.WORKLOAD_FEDERATION_PREFIX)
    # Federation Name shares the per-run uuid suffix with the IAM username
    # so CloudTrail events from the same probe correlate.
    assert federation_name.removeprefix(short_lived_module.WORKLOAD_FEDERATION_PREFIX) == username.removeprefix(
        short_lived_module.TEST_USER_PREFIX
    )
    assert sts.federation_calls[0]["Policy"] == short_lived_module.DENY_ALL_POLICY


def test_short_lived_credentials_main_fails_when_node_ttl_exceeds_bound(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    short_lived_module: ModuleType,
) -> None:
    """Node TTL above the configured bound fails the within-bound probe and still cleans up."""
    from datetime import datetime, timedelta

    now = datetime.now(UTC)
    iam = FakeShortLivedIam()
    sts = FakeShortLivedSts(
        session_expiration=now + timedelta(seconds=7200),
        federation_expiration=now + timedelta(seconds=1800),
    )
    _patch_short_lived_clients(monkeypatch, short_lived_module, iam=iam, sts=sts)
    _set_short_lived_argv(monkeypatch, short_lived_module, "--max-ttl-seconds", "3600")

    exit_code = short_lived_module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["success"] is False
    assert payload["tests"]["node_credential_has_expiry"]["passed"] is True
    assert payload["tests"]["node_credential_ttl_within_bound"]["passed"] is False
    assert "outside" in payload["tests"]["node_credential_ttl_within_bound"]["error"]
    assert payload["tests"]["workload_credential_ttl_within_bound"]["passed"] is True
    assert iam.deleted_users  # cleanup still ran on probe failure


def test_short_lived_credentials_main_skips_when_create_user_denied(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    short_lived_module: ModuleType,
) -> None:
    """Orchestrator principal lacking iam:CreateUser yields a clean skip and never probes STS."""
    iam = FakeShortLivedIam(
        create_user_error=_client_error(
            "CreateUser", code="AccessDenied", message="not authorized to perform iam:CreateUser"
        ),
    )
    sts = FakeShortLivedSts()
    _patch_short_lived_clients(monkeypatch, short_lived_module, iam=iam, sts=sts)
    _set_short_lived_argv(monkeypatch, short_lived_module)

    exit_code = short_lived_module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["success"] is True
    assert payload["skipped"] is True
    # Skip reason includes the failing operation name, AWS error code, and
    # the underlying message so operators don't need to re-run with debug
    # to figure out what was denied.
    assert "CreateUser" in payload["skip_reason"]
    assert "AccessDenied" in payload["skip_reason"]
    assert "not authorized to perform iam:CreateUser" in payload["skip_reason"]
    assert payload["tests"] == {}
    assert sts.session_call_count == 0
    assert sts.federation_calls == []
    assert iam.deleted_users == []  # nothing was created


def test_short_lived_credentials_main_cleans_up_when_put_user_policy_fails(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    short_lived_module: ModuleType,
) -> None:
    """Non-skippable failure on PutUserPolicy must still delete the user that was just created."""
    iam = FakeShortLivedIam(
        put_user_policy_error=_client_error("PutUserPolicy", code="LimitExceeded"),
    )
    sts = FakeShortLivedSts()
    _patch_short_lived_clients(monkeypatch, short_lived_module, iam=iam, sts=sts)
    _set_short_lived_argv(monkeypatch, short_lived_module)

    exit_code = short_lived_module.main()

    assert exit_code == 1
    assert len(iam.created_users) == 1
    username = iam.created_users[0]["UserName"]
    assert iam.deleted_users == [username]
    assert sts.session_call_count == 0  # no probes attempted
    assert sts.federation_calls == []


def test_short_lived_credentials_main_cleans_up_when_create_access_key_fails(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    short_lived_module: ModuleType,
) -> None:
    """Non-skippable failure on CreateAccessKey must still detach inline policy and delete the user."""
    iam = FakeShortLivedIam(
        create_access_key_error=_client_error("CreateAccessKey", code="LimitExceeded"),
    )
    sts = FakeShortLivedSts()
    _patch_short_lived_clients(monkeypatch, short_lived_module, iam=iam, sts=sts)
    _set_short_lived_argv(monkeypatch, short_lived_module)

    exit_code = short_lived_module.main()

    assert exit_code == 1
    assert len(iam.created_users) == 1
    username = iam.created_users[0]["UserName"]
    assert iam.deleted_policies == [(username, short_lived_module.INLINE_POLICY_NAME)]
    assert iam.deleted_users == [username]
    assert sts.session_call_count == 0


def test_short_lived_credentials_main_skips_and_cleans_up_when_put_user_policy_denied(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    short_lived_module: ModuleType,
) -> None:
    """Skip path on a partial-setup AccessDenied still deletes the user and surfaces the AWS message."""
    iam = FakeShortLivedIam(
        put_user_policy_error=_client_error(
            "PutUserPolicy",
            code="AccessDenied",
            message="not authorized to perform iam:PutUserPolicy",
        ),
    )
    sts = FakeShortLivedSts()
    _patch_short_lived_clients(monkeypatch, short_lived_module, iam=iam, sts=sts)
    _set_short_lived_argv(monkeypatch, short_lived_module)

    exit_code = short_lived_module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["skipped"] is True
    assert "PutUserPolicy" in payload["skip_reason"]
    assert "AccessDenied" in payload["skip_reason"]
    assert "not authorized to perform iam:PutUserPolicy" in payload["skip_reason"]
    assert len(iam.created_users) == 1
    assert iam.deleted_users == [iam.created_users[0]["UserName"]]


def test_short_lived_credentials_main_fails_when_skip_path_cleanup_fails(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    short_lived_module: ModuleType,
) -> None:
    """Skip-eligible setup error + cleanup failure must surface as a hard failure, never a clean skip.

    Otherwise we'd report ``skipped: true`` while leaving an IAM user
    behind in the account.
    """
    iam = FakeShortLivedIam(
        put_user_policy_error=_client_error("PutUserPolicy", code="AccessDenied"),
        delete_user_error=_client_error("DeleteUser", code="ServiceUnavailable"),
    )
    sts = FakeShortLivedSts()
    _patch_short_lived_clients(monkeypatch, short_lived_module, iam=iam, sts=sts)
    _set_short_lived_argv(monkeypatch, short_lived_module)

    exit_code = short_lived_module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["success"] is False
    assert payload.get("skipped") is not True
    assert "cleanup_errors" in payload
    assert "setup failed" in payload["error"]
    assert "cleanup failed" in payload["error"]
    assert any("delete user" in err for err in payload["cleanup_errors"])


def test_short_lived_credentials_main_retries_node_probe_on_eventual_consistency(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    short_lived_module: ModuleType,
) -> None:
    """A burst of InvalidClientTokenId errors is retried until STS sees the new key."""
    from datetime import datetime, timedelta

    now = datetime.now(UTC)
    iam = FakeShortLivedIam()
    sts = FakeShortLivedSts(
        session_expiration=now + timedelta(seconds=3600),
        federation_expiration=now + timedelta(seconds=3600),
        session_errors=[
            _client_error("GetSessionToken", code="InvalidClientTokenId"),
            _client_error("GetSessionToken", code="InvalidClientTokenId"),
        ],
    )
    _patch_short_lived_clients(monkeypatch, short_lived_module, iam=iam, sts=sts)
    _set_short_lived_argv(monkeypatch, short_lived_module)

    exit_code = short_lived_module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["success"] is True
    assert sts.session_call_count == 3  # two failures plus one success
    assert iam.deleted_users  # cleanup still ran


def test_short_lived_credentials_main_unhandled_node_error_fails(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    short_lived_module: ModuleType,
) -> None:
    """Non-retryable STS errors on the node probe surface as a failure (not a skip)."""
    iam = FakeShortLivedIam()
    sts = FakeShortLivedSts(
        session_errors=[_client_error("GetSessionToken", code="ServiceUnavailable")],
    )
    _patch_short_lived_clients(monkeypatch, short_lived_module, iam=iam, sts=sts)
    _set_short_lived_argv(monkeypatch, short_lived_module)

    exit_code = short_lived_module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["success"] is False
    assert payload.get("skipped") is not True
    assert iam.deleted_users  # cleanup still ran via the decorator-caught path


def test_short_lived_credentials_main_records_workload_error_and_keeps_node_pass(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    short_lived_module: ModuleType,
) -> None:
    """A workload-side STS error is captured per-probe with op + code + message; node probe still passes."""
    from datetime import datetime, timedelta

    now = datetime.now(UTC)
    iam = FakeShortLivedIam()
    sts = FakeShortLivedSts(
        session_expiration=now + timedelta(seconds=3600),
        federation_error=_client_error(
            "GetFederationToken",
            code="AccessDenied",
            message="not authorized to perform sts:GetFederationToken",
        ),
    )
    _patch_short_lived_clients(monkeypatch, short_lived_module, iam=iam, sts=sts)
    _set_short_lived_argv(monkeypatch, short_lived_module)

    exit_code = short_lived_module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["success"] is False
    assert payload.get("skipped") is not True
    assert payload["tests"]["node_credential_has_expiry"]["passed"] is True
    assert payload["tests"]["node_credential_ttl_within_bound"]["passed"] is True
    assert payload["tests"]["workload_credential_has_expiry"]["passed"] is False
    workload_error = payload["tests"]["workload_credential_has_expiry"]["error"]
    assert "GetFederationToken" in workload_error
    assert "AccessDenied" in workload_error
    assert "not authorized to perform sts:GetFederationToken" in workload_error
    assert iam.deleted_users  # cleanup ran


def test_short_lived_credentials_main_handles_missing_expiration(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    short_lived_module: ModuleType,
) -> None:
    """Missing Credentials.Expiration in either response surfaces as a per-probe error."""
    from datetime import datetime, timedelta

    now = datetime.now(UTC)
    iam = FakeShortLivedIam()
    sts = FakeShortLivedSts(
        omit_session_expiration=True,
        federation_expiration=now + timedelta(seconds=1800),
    )
    _patch_short_lived_clients(monkeypatch, short_lived_module, iam=iam, sts=sts)
    _set_short_lived_argv(monkeypatch, short_lived_module)

    exit_code = short_lived_module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["success"] is False
    assert payload["tests"]["node_credential_has_expiry"]["passed"] is False
    assert "Expiration missing" in payload["tests"]["node_credential_has_expiry"]["error"]
    assert payload["tests"]["workload_credential_has_expiry"]["passed"] is True


def test_short_lived_credentials_main_records_cleanup_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    short_lived_module: ModuleType,
) -> None:
    """Successful probes are reported failed when IAM cleanup fails."""
    from datetime import datetime, timedelta

    now = datetime.now(UTC)
    iam = FakeShortLivedIam(delete_user_error=_client_error("DeleteUser", code="ServiceUnavailable"))
    sts = FakeShortLivedSts(
        session_expiration=now + timedelta(seconds=3600),
        federation_expiration=now + timedelta(seconds=3600),
    )
    _patch_short_lived_clients(monkeypatch, short_lived_module, iam=iam, sts=sts)
    _set_short_lived_argv(monkeypatch, short_lived_module)

    exit_code = short_lived_module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["success"] is False
    assert "cleanup_errors" in payload
    assert any("delete user" in err for err in payload["cleanup_errors"])
    assert "Cleanup failed" in payload["error"]


def test_short_lived_credentials_main_skips_for_non_positive_max_ttl(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    short_lived_module: ModuleType,
) -> None:
    """A non-positive --max-ttl-seconds yields a clean skip rather than a hard fail or any AWS calls."""
    iam = FakeShortLivedIam()
    sts = FakeShortLivedSts()
    _patch_short_lived_clients(monkeypatch, short_lived_module, iam=iam, sts=sts)
    _set_short_lived_argv(monkeypatch, short_lived_module, "--max-ttl-seconds", "0")

    exit_code = short_lived_module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["skipped"] is True
    assert "positive integer" in payload["skip_reason"]
    assert iam.created_users == []
    assert sts.session_call_count == 0


def test_short_lived_credentials_cleanup_handles_partial_setup(
    short_lived_module: ModuleType,
) -> None:
    """_cleanup_test_user is no-op for an unset username and skips inline policy when user_created is False."""
    iam = FakeShortLivedIam()
    assert short_lived_module._cleanup_test_user(iam, None, None, False) == []
    assert short_lived_module._cleanup_test_user(iam, "isv-sec02-test-xyz", None, False) == []
    assert iam.deleted_policies == []
    assert iam.deleted_users == []
