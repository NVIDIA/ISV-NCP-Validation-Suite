# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Shared VPC test helpers.

Provides common VPC operations used across network test scripts:
- VPC creation with tagging and optional DNS
- VPC cleanup / deletion
"""

from __future__ import annotations

from typing import Any

from botocore.exceptions import ClientError


def create_test_vpc(
    ec2: Any,
    cidr: str,
    name: str,
    *,
    enable_dns: bool = False,
) -> dict[str, Any]:
    """Create a tagged test VPC and wait for it to become available.

    Args:
        ec2: Boto3 EC2 client.
        cidr: CIDR block for the VPC (e.g., "10.94.0.0/16").
        name: Name tag for the VPC.
        enable_dns: If True, enable DNS support and hostnames on the VPC.

    Returns:
        Dict with keys: passed, vpc_id, cidr, message/error.
    """
    result: dict[str, Any] = {"passed": False}
    try:
        vpc = ec2.create_vpc(CidrBlock=cidr)
        vpc_id = vpc["Vpc"]["VpcId"]

        ec2.create_tags(
            Resources=[vpc_id],
            Tags=[
                {"Key": "Name", "Value": name},
                {"Key": "CreatedBy", "Value": "isvtest"},
            ],
        )

        waiter = ec2.get_waiter("vpc_available")
        waiter.wait(VpcIds=[vpc_id])

        if enable_dns:
            ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsSupport={"Value": True})
            ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsHostnames={"Value": True})

        result["passed"] = True
        result["vpc_id"] = vpc_id
        result["cidr"] = cidr
        result["message"] = f"Created VPC {vpc_id}"
    except ClientError as e:
        result["error"] = str(e)

    return result


def delete_vpc(ec2: Any, vpc_id: str) -> None:
    """Delete a VPC, ignoring errors if it no longer exists.

    Args:
        ec2: Boto3 EC2 client.
        vpc_id: VPC ID to delete.
    """
    try:
        ec2.delete_vpc(VpcId=vpc_id)
    except ClientError:
        pass


def cleanup_vpc_resources(
    ec2: Any,
    vpc_id: str,
    *,
    subnet_ids: list[str] | None = None,
    sg_ids: list[str] | None = None,
    nacl_ids: list[str] | None = None,
) -> None:
    """Clean up VPC and associated resources, ignoring individual errors.

    Deletes resources in dependency order: SGs -> NACLs -> subnets -> VPC.

    Args:
        ec2: Boto3 EC2 client.
        vpc_id: VPC ID to clean up.
        subnet_ids: Subnet IDs to delete.
        sg_ids: Security group IDs to delete.
        nacl_ids: Network ACL IDs to delete.
    """
    for sg_id in sg_ids or []:
        try:
            ec2.delete_security_group(GroupId=sg_id)
        except ClientError:
            pass

    for nacl_id in nacl_ids or []:
        try:
            ec2.delete_network_acl(NetworkAclId=nacl_id)
        except ClientError:
            pass

    for subnet_id in subnet_ids or []:
        try:
            ec2.delete_subnet(SubnetId=subnet_id)
        except ClientError:
            pass

    delete_vpc(ec2, vpc_id)
