# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Tests for AWS network reference scripts."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from botocore.exceptions import ClientError

ISVCTL_ROOT = Path(__file__).resolve().parents[1]
AWS_NETWORK_SCRIPTS = ISVCTL_ROOT / "configs" / "providers" / "aws" / "scripts" / "network"


def _load_network_script(script_name: str) -> ModuleType:
    """Load an AWS network script as a module for direct helper testing."""
    script_path = AWS_NETWORK_SCRIPTS / script_name
    spec = importlib.util.spec_from_file_location(f"test_{script_path.stem}", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _client_error(operation_name: str, code: str = "AccessDenied", message: str = "denied") -> ClientError:
    """Create a botocore ClientError for fake AWS client failures."""
    return ClientError({"Error": {"Code": code, "Message": message}}, operation_name)


class FakeServiceScopingEc2:
    """Fake EC2 client covering the calls used by test_service_scoping."""

    def __init__(
        self,
        endpoint_eni_ids: list[str] | None = None,
        delete_endpoint_error: ClientError | None = None,
        *,
        endpoint_deleted_after_delete: bool = True,
        delete_endpoint_unsuccessful: list[dict[str, Any]] | None = None,
        subnet_dependency_failures: int = 0,
        sg_dependency_failures: int = 0,
    ) -> None:
        """Configure ENIs returned by the endpoint and optional delete failure."""
        self.endpoint_eni_ids = endpoint_eni_ids if endpoint_eni_ids is not None else ["eni-endpoint-1"]
        self.delete_endpoint_error = delete_endpoint_error
        self.endpoint_deleted_after_delete = endpoint_deleted_after_delete
        self.delete_endpoint_unsuccessful = delete_endpoint_unsuccessful or []
        self.subnet_dependency_failures = subnet_dependency_failures
        self.sg_dependency_failures = sg_dependency_failures
        self.delete_subnet_attempts = 0
        self.delete_sg_attempts = 0
        self.created_sg_ingress: list[dict[str, Any]] = []
        self.deleted_endpoints: list[str] = []
        self.deleted_subnets: list[str] = []
        self.deleted_sgs: list[str] = []
        self.deleted_enis: list[str] = []

    def create_subnet(self, VpcId: str, CidrBlock: str, AvailabilityZone: str) -> dict[str, Any]:
        """Return a fake subnet."""
        return {"Subnet": {"SubnetId": "subnet-aaa", "VpcId": VpcId, "CidrBlock": CidrBlock}}

    def create_security_group(
        self,
        GroupName: str,
        Description: str,
        VpcId: str,
        TagSpecifications: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Return a fake SG ID."""
        return {"GroupId": "sg-svc"}

    def authorize_security_group_ingress(self, GroupId: str, IpPermissions: list[dict[str, Any]]) -> dict[str, Any]:
        """Record the SG rule that was authorized."""
        self.created_sg_ingress.append({"GroupId": GroupId, "IpPermissions": IpPermissions})
        return {}

    def create_vpc_endpoint(
        self,
        VpcId: str,
        ServiceName: str,
        VpcEndpointType: str,
        SubnetIds: list[str],
        SecurityGroupIds: list[str],
        PrivateDnsEnabled: bool,
        TagSpecifications: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Return a fake VPC interface endpoint."""
        assert VpcEndpointType == "Interface"
        assert ServiceName.startswith("com.amazonaws.")
        assert PrivateDnsEnabled is False
        return {"VpcEndpoint": {"VpcEndpointId": "vpce-svc"}}

    def create_network_interface(self, SubnetId: str, **kwargs: Any) -> dict[str, Any]:
        """Return a fake unrelated ENI without an SG."""
        return {"NetworkInterface": {"NetworkInterfaceId": "eni-other"}}

    def describe_vpc_endpoints(self, VpcEndpointIds: list[str]) -> dict[str, Any]:
        """Report the endpoint with its ENI IDs (or absence after deletion)."""
        if VpcEndpointIds[0] in self.deleted_endpoints and self.endpoint_deleted_after_delete:
            return {"VpcEndpoints": []}
        return {
            "VpcEndpoints": [
                {
                    "VpcEndpointId": VpcEndpointIds[0],
                    "NetworkInterfaceIds": list(self.endpoint_eni_ids),
                    "State": "available",
                }
            ]
        }

    def describe_network_interfaces(self, NetworkInterfaceIds: list[str]) -> dict[str, Any]:
        """Report SG attachment: SG attached to endpoint ENIs, none on the unrelated ENI."""
        nics = []
        for nic_id in NetworkInterfaceIds:
            if nic_id in self.endpoint_eni_ids:
                nics.append({"NetworkInterfaceId": nic_id, "Groups": [{"GroupId": "sg-svc"}]})
            else:
                nics.append({"NetworkInterfaceId": nic_id, "Groups": []})
        return {"NetworkInterfaces": nics}

    def delete_vpc_endpoints(self, VpcEndpointIds: list[str]) -> dict[str, Any]:
        """Delete the endpoint, optionally raising a configured error."""
        if self.delete_endpoint_error:
            raise self.delete_endpoint_error
        self.deleted_endpoints.extend(VpcEndpointIds)
        return {"Unsuccessful": self.delete_endpoint_unsuccessful}

    def delete_network_interface(self, NetworkInterfaceId: str) -> None:
        """Delete a fake ENI."""
        self.deleted_enis.append(NetworkInterfaceId)

    def delete_subnet(self, SubnetId: str) -> None:
        """Delete a fake subnet."""
        self.delete_subnet_attempts += 1
        if self.delete_subnet_attempts <= self.subnet_dependency_failures:
            raise _client_error("DeleteSubnet", "DependencyViolation", "subnet has dependencies")
        self.deleted_subnets.append(SubnetId)

    def delete_security_group(self, GroupId: str) -> None:
        """Delete a fake SG."""
        self.delete_sg_attempts += 1
        if self.delete_sg_attempts <= self.sg_dependency_failures:
            raise _client_error("DeleteSecurityGroup", "DependencyViolation", "SG has dependencies")
        self.deleted_sgs.append(GroupId)


def test_service_scoping_happy_path_attaches_sg_only_to_endpoint_eni(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SG must attach to the endpoint's ENIs and not to the unrelated ENI."""
    module = _load_network_script("sg_scoping_test.py")
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    ec2 = FakeServiceScopingEc2(endpoint_eni_ids=["eni-endpoint-1", "eni-endpoint-2"])

    result = module.test_service_scoping(ec2, "vpc-test", "us-west-2a", "us-west-2")

    assert result["create_sg"]["passed"] is True
    assert result["apply_service_rule"]["passed"] is True
    assert result["service_endpoint_allowed"]["passed"] is True
    assert result["other_endpoint_blocked"]["passed"] is True
    assert result["cleanup"]["passed"] is True
    assert ec2.created_sg_ingress[0]["IpPermissions"][0]["FromPort"] == 443
    assert ec2.created_sg_ingress[0]["IpPermissions"][0]["ToPort"] == 443
    assert ec2.deleted_endpoints == ["vpce-svc"]
    assert ec2.deleted_enis == ["eni-other"]
    assert ec2.deleted_subnets == ["subnet-aaa"]
    assert ec2.deleted_sgs == ["sg-svc"]


def test_service_scoping_records_cleanup_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed VPC endpoint deletion is reported via the cleanup result."""
    module = _load_network_script("sg_scoping_test.py")
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    ec2 = FakeServiceScopingEc2(
        endpoint_eni_ids=["eni-endpoint-1"],
        delete_endpoint_error=_client_error("DeleteVpcEndpoints"),
    )

    result = module.test_service_scoping(ec2, "vpc-test", "us-west-2a", "us-west-2")

    assert result["service_endpoint_allowed"]["passed"] is True
    assert result["cleanup"]["passed"] is False
    assert "delete VPC endpoint vpce-svc" in result["cleanup"]["error"]


def test_service_scoping_records_endpoint_delete_unsuccessful(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unsuccessful delete_vpc_endpoints entries should fail cleanup."""
    module = _load_network_script("sg_scoping_test.py")
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    ec2 = FakeServiceScopingEc2(
        endpoint_eni_ids=["eni-endpoint-1"],
        delete_endpoint_unsuccessful=[{"ResourceId": "vpce-svc", "Error": {"Code": "UnauthorizedOperation"}}],
    )

    result = module.test_service_scoping(ec2, "vpc-test", "us-west-2a", "us-west-2")

    assert result["cleanup"]["passed"] is False
    assert "delete_vpc_endpoints reported unsuccessful entries" in result["cleanup"]["error"]
    assert ec2.deleted_enis == ["eni-other"]
    assert ec2.deleted_subnets == ["subnet-aaa"]
    assert ec2.deleted_sgs == ["sg-svc"]


def test_service_scoping_records_endpoint_wait_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Endpoint deletion wait timeouts should be the visible cleanup cause."""
    module = _load_network_script("sg_scoping_test.py")
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    ec2 = FakeServiceScopingEc2(
        endpoint_eni_ids=["eni-endpoint-1"],
        endpoint_deleted_after_delete=False,
    )

    result = module.test_service_scoping(ec2, "vpc-test", "us-west-2a", "us-west-2")

    assert result["cleanup"]["passed"] is False
    assert result["cleanup"]["error"].startswith("delete VPC endpoint vpce-svc: Timed out waiting")
    assert ec2.deleted_enis == ["eni-other"]
    assert ec2.deleted_subnets == ["subnet-aaa"]
    assert ec2.deleted_sgs == ["sg-svc"]


def test_service_scoping_retries_dependency_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Subnet and SG cleanup should retry brief dependency lag after endpoint deletion."""
    module = _load_network_script("sg_scoping_test.py")
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    ec2 = FakeServiceScopingEc2(
        endpoint_eni_ids=["eni-endpoint-1"],
        subnet_dependency_failures=2,
        sg_dependency_failures=1,
    )

    result = module.test_service_scoping(ec2, "vpc-test", "us-west-2a", "us-west-2")

    assert result["cleanup"]["passed"] is True
    assert ec2.delete_subnet_attempts == 3
    assert ec2.delete_sg_attempts == 2
    assert ec2.deleted_subnets == ["subnet-aaa"]
    assert ec2.deleted_sgs == ["sg-svc"]


class FakeEndpointDeletionWaitEc2:
    """Fake EC2 client for endpoint deletion polling."""

    def __init__(self, error: ClientError) -> None:
        """Configure the error raised by describe_vpc_endpoints."""
        self.error = error

    def describe_vpc_endpoints(self, VpcEndpointIds: list[str]) -> dict[str, Any]:
        """Raise the configured describe error."""
        raise self.error


def test_wait_for_endpoint_deletion_treats_not_found_as_success() -> None:
    """AWS NotFound during endpoint deletion means the endpoint is already gone."""
    module = _load_network_script("sg_scoping_test.py")
    ec2 = FakeEndpointDeletionWaitEc2(
        _client_error("DescribeVpcEndpoints", "InvalidVpcEndpointId.NotFound", "endpoint not found")
    )

    module._wait_for_endpoint_deletion(ec2, "vpce-svc", attempts=1, delay=0)


def test_wait_for_endpoint_deletion_reraises_unexpected_client_error() -> None:
    """Unexpected describe errors should still fail cleanup."""
    module = _load_network_script("sg_scoping_test.py")
    ec2 = FakeEndpointDeletionWaitEc2(_client_error("DescribeVpcEndpoints", "RequestLimitExceeded", "throttled"))

    with pytest.raises(ClientError):
        module._wait_for_endpoint_deletion(ec2, "vpce-svc", attempts=1, delay=0)


class FakeNeverDeletedEndpointEc2:
    """Fake EC2 client that keeps reporting the endpoint as present."""

    def describe_vpc_endpoints(self, VpcEndpointIds: list[str]) -> dict[str, Any]:
        """Report a still-present endpoint."""
        return {
            "VpcEndpoints": [
                {
                    "VpcEndpointId": VpcEndpointIds[0],
                    "NetworkInterfaceIds": ["eni-endpoint-1"],
                    "State": "deleting",
                }
            ]
        }


def test_wait_for_endpoint_deletion_raises_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Polling exhaustion must surface as a timeout instead of returning success."""
    module = _load_network_script("sg_scoping_test.py")
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    ec2 = FakeNeverDeletedEndpointEc2()

    with pytest.raises(TimeoutError, match="Timed out waiting for VPC endpoint vpce-svc deletion"):
        module._wait_for_endpoint_deletion(ec2, "vpce-svc", attempts=2, delay=0)
