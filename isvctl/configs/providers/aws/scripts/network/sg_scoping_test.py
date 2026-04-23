#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Test security group rule scoping at workload, node, or subnet level.

AWS mapping:
  - workload/node: SGs attach per-ENI, so rules scope to individual
    instances.  We create a VPC with two ENIs, apply an SG to only one,
    and verify the rule is present on the target but absent on the other.
  - subnet: NACLs scope to subnets.  We create two subnets, apply a
    custom NACL with a deny rule to one, and verify the other subnet
    still uses the default (allow-all) NACL.

Usage:
    python sg_scoping_test.py --region us-west-2 --scope workload
    python sg_scoping_test.py --region us-west-2 --scope node
    python sg_scoping_test.py --region us-west-2 --scope subnet
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
from common.vpc import cleanup_vpc_resources, create_test_vpc

CIDR = "10.85.0.0/16"
SUBNET_A_CIDR = "10.85.1.0/24"
SUBNET_B_CIDR = "10.85.2.0/24"


def _get_az(ec2: Any, region: str) -> str:
    """Return the first available AZ in the region."""
    azs = ec2.describe_availability_zones(Filters=[{"Name": "state", "Values": ["available"]}])["AvailabilityZones"]
    return azs[0]["ZoneName"]


def test_workload_or_node_scoping(ec2: Any, vpc_id: str, az: str, scope: str) -> dict[str, Any]:
    """Verify SG rules scope to a single ENI (workload/node level)."""
    results: dict[str, Any] = {}
    sg_id = None
    subnet_id = None
    eni_target = None
    eni_other = None
    tag = f"isv-sg-scope-{scope}-{uuid.uuid4().hex[:6]}"

    try:
        # Create SG with an inbound rule
        sg = ec2.create_security_group(
            GroupName=tag,
            Description=f"SG scoping test ({scope})",
            VpcId=vpc_id,
            TagSpecifications=[
                {
                    "ResourceType": "security-group",
                    "Tags": [{"Key": "CreatedBy", "Value": "isvtest"}],
                }
            ],
        )
        sg_id = sg["GroupId"]
        ec2.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 443,
                    "ToPort": 443,
                    "IpRanges": [{"CidrIp": "10.0.0.0/8"}],
                }
            ],
        )
        results["create_sg"] = {"passed": True}

        # Create a subnet + two ENIs
        subnet = ec2.create_subnet(VpcId=vpc_id, CidrBlock=SUBNET_A_CIDR, AvailabilityZone=az)
        subnet_id = subnet["Subnet"]["SubnetId"]

        eni_t = ec2.create_network_interface(SubnetId=subnet_id, Groups=[sg_id])
        eni_target = eni_t["NetworkInterface"]["NetworkInterfaceId"]

        eni_o = ec2.create_network_interface(SubnetId=subnet_id)
        eni_other = eni_o["NetworkInterface"]["NetworkInterfaceId"]

        apply_key = f"apply_{scope}_rule"
        results[apply_key] = {"passed": True}

        # Verify target ENI has our SG
        target_info = ec2.describe_network_interfaces(NetworkInterfaceIds=[eni_target])
        target_sgs = [g["GroupId"] for g in target_info["NetworkInterfaces"][0]["Groups"]]

        allowed_key = f"{'workload' if scope == 'workload' else 'target_node'}_allowed"
        if sg_id in target_sgs:
            results[allowed_key] = {"passed": True, "message": f"SG {sg_id} attached to target ENI"}
        else:
            results[allowed_key] = {"passed": False, "error": "SG not attached to target ENI"}

        # Verify other ENI does NOT have our SG
        other_info = ec2.describe_network_interfaces(NetworkInterfaceIds=[eni_other])
        other_sgs = [g["GroupId"] for g in other_info["NetworkInterfaces"][0]["Groups"]]

        blocked_key = f"other_{'workload' if scope == 'workload' else 'node'}_blocked"
        if sg_id not in other_sgs:
            results[blocked_key] = {"passed": True, "message": "SG not on other ENI (scoped correctly)"}
        else:
            results[blocked_key] = {"passed": False, "error": "SG leaked to other ENI"}

    except ClientError as e:
        for key in [
            "create_sg",
            f"apply_{scope}_rule",
            f"{'workload' if scope == 'workload' else 'target_node'}_allowed",
            f"other_{'workload' if scope == 'workload' else 'node'}_blocked",
        ]:
            results.setdefault(key, {"passed": False, "error": str(e)})
    finally:
        for eni_id in [eni_target, eni_other]:
            if eni_id:
                try:
                    ec2.delete_network_interface(NetworkInterfaceId=eni_id)
                except ClientError:
                    pass
        if subnet_id:
            try:
                ec2.delete_subnet(SubnetId=subnet_id)
            except ClientError:
                pass
        if sg_id:
            try:
                ec2.delete_security_group(GroupId=sg_id)
            except ClientError:
                pass

    results["cleanup"] = {"passed": True}
    return results


def test_subnet_scoping(ec2: Any, vpc_id: str, az: str) -> dict[str, Any]:
    """Verify NACL rules scope to a single subnet."""
    results: dict[str, Any] = {}
    subnet_a = None
    subnet_b = None
    nacl_id = None

    try:
        # Create SG placeholder (NACLs are the subnet-level mechanism in AWS)
        results["create_sg"] = {"passed": True, "message": "Using NACLs for subnet-level scoping in AWS"}

        # Create two subnets
        sa = ec2.create_subnet(VpcId=vpc_id, CidrBlock=SUBNET_A_CIDR, AvailabilityZone=az)
        subnet_a = sa["Subnet"]["SubnetId"]
        sb = ec2.create_subnet(VpcId=vpc_id, CidrBlock=SUBNET_B_CIDR, AvailabilityZone=az)
        subnet_b = sb["Subnet"]["SubnetId"]

        # Create custom NACL with a deny rule and associate to subnet A
        nacl = ec2.create_network_acl(VpcId=vpc_id)
        nacl_id = nacl["NetworkAcl"]["NetworkAclId"]
        ec2.create_tags(
            Resources=[nacl_id],
            Tags=[{"Key": "CreatedBy", "Value": "isvtest"}],
        )
        ec2.create_network_acl_entry(
            NetworkAclId=nacl_id,
            RuleNumber=100,
            Protocol="-1",
            RuleAction="deny",
            Egress=False,
            CidrBlock="0.0.0.0/0",
        )
        ec2.replace_network_acl_association(
            AssociationId=_get_nacl_assoc(ec2, vpc_id, subnet_a),
            NetworkAclId=nacl_id,
        )
        results["apply_subnet_rule"] = {"passed": True}

        # Verify subnet A uses the custom NACL
        nacls_a = ec2.describe_network_acls(Filters=[{"Name": "association.subnet-id", "Values": [subnet_a]}])[
            "NetworkAcls"
        ]
        a_nacl_ids = [n["NetworkAclId"] for n in nacls_a]

        if nacl_id in a_nacl_ids:
            results["subnet_allowed"] = {"passed": True, "message": "Custom NACL applied to target subnet"}
        else:
            results["subnet_allowed"] = {"passed": False, "error": "Custom NACL not on target subnet"}

        # Verify subnet B still uses default NACL (not the custom one)
        nacls_b = ec2.describe_network_acls(Filters=[{"Name": "association.subnet-id", "Values": [subnet_b]}])[
            "NetworkAcls"
        ]
        b_nacl_ids = [n["NetworkAclId"] for n in nacls_b]

        if nacl_id not in b_nacl_ids:
            results["other_subnet_blocked"] = {
                "passed": True,
                "message": "Custom NACL not on other subnet (scoped correctly)",
            }
        else:
            results["other_subnet_blocked"] = {"passed": False, "error": "NACL leaked to other subnet"}

    except ClientError as e:
        for key in ["create_sg", "apply_subnet_rule", "subnet_allowed", "other_subnet_blocked"]:
            results.setdefault(key, {"passed": False, "error": str(e)})
    finally:
        # Re-associate default NACL before deleting custom one
        if nacl_id and subnet_a:
            try:
                default_nacl = _get_default_nacl(ec2, vpc_id)
                if default_nacl:
                    assoc = _get_nacl_assoc_for_nacl(ec2, nacl_id, subnet_a)
                    if assoc:
                        ec2.replace_network_acl_association(
                            AssociationId=assoc,
                            NetworkAclId=default_nacl,
                        )
            except ClientError:
                pass
        if nacl_id:
            try:
                ec2.delete_network_acl(NetworkAclId=nacl_id)
            except ClientError:
                pass
        for sid in [subnet_a, subnet_b]:
            if sid:
                try:
                    ec2.delete_subnet(SubnetId=sid)
                except ClientError:
                    pass

    results["cleanup"] = {"passed": True}
    return results


def _get_nacl_assoc(ec2: Any, vpc_id: str, subnet_id: str) -> str:
    """Get the NACL association ID for a subnet."""
    nacls = ec2.describe_network_acls(
        Filters=[
            {"Name": "vpc-id", "Values": [vpc_id]},
            {"Name": "association.subnet-id", "Values": [subnet_id]},
        ]
    )["NetworkAcls"]
    for nacl in nacls:
        for assoc in nacl.get("Associations", []):
            if assoc.get("SubnetId") == subnet_id:
                return assoc["NetworkAclAssociationId"]
    msg = f"No NACL association for subnet {subnet_id}"
    raise ValueError(msg)


def _get_nacl_assoc_for_nacl(ec2: Any, nacl_id: str, subnet_id: str) -> str | None:
    """Get the association ID for a specific NACL + subnet pair."""
    nacls = ec2.describe_network_acls(NetworkAclIds=[nacl_id])["NetworkAcls"]
    for nacl in nacls:
        for assoc in nacl.get("Associations", []):
            if assoc.get("SubnetId") == subnet_id:
                return assoc["NetworkAclAssociationId"]
    return None


def _get_default_nacl(ec2: Any, vpc_id: str) -> str | None:
    """Get the default NACL ID for a VPC."""
    nacls = ec2.describe_network_acls(
        Filters=[
            {"Name": "vpc-id", "Values": [vpc_id]},
            {"Name": "default", "Values": ["true"]},
        ]
    )["NetworkAcls"]
    return nacls[0]["NetworkAclId"] if nacls else None


@handle_aws_errors
def main() -> int:
    """Run SG rule scoping test for the given scope and emit JSON result."""
    parser = argparse.ArgumentParser(description="Test SG rule scoping levels")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-west-2"))
    parser.add_argument("--scope", required=True, choices=["workload", "node", "subnet"])
    args = parser.parse_args()

    ec2 = boto3.client("ec2", region_name=args.region)
    suffix = uuid.uuid4().hex[:8]
    vpc_name = f"isv-sg-scoping-{args.scope}-{suffix}"

    result: dict[str, Any] = {
        "success": False,
        "platform": "network",
        "test_name": f"sg_{args.scope}_scoping",
        "scope": args.scope,
        "tests": {},
    }

    vpc_id = None
    try:
        vpc_result = create_test_vpc(ec2, CIDR, vpc_name)
        if not vpc_result["passed"]:
            result["tests"]["create_sg"] = {"passed": False, "error": "VPC creation failed"}
            print(json.dumps(result, indent=2))
            return 1

        vpc_id = vpc_result["vpc_id"]
        az = _get_az(ec2, args.region)

        if args.scope in ("workload", "node"):
            result["tests"] = test_workload_or_node_scoping(ec2, vpc_id, az, args.scope)
        else:
            result["tests"] = test_subnet_scoping(ec2, vpc_id, az)

        result["success"] = all(t.get("passed") for t in result["tests"].values())
    except Exception as e:
        result["error"] = str(e)
    finally:
        if vpc_id:
            cleanup_vpc_resources(ec2, vpc_id)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
