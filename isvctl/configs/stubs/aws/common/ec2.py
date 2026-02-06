"""Shared EC2 helper utilities.

Provides common EC2 operations used across VM and ISO launch scripts:
- Key pair creation with idempotent handling
- Security group creation with SSH ingress
- Availability zone support detection
- Default VPC and subnet discovery
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from botocore.exceptions import ClientError


def get_supported_azs(ec2: Any, instance_type: str) -> set[str]:
    """Get availability zones that support the given instance type.

    Args:
        ec2: Boto3 EC2 client.
        instance_type: EC2 instance type to check (e.g., 'g4dn.xlarge').

    Returns:
        Set of availability zone names, or empty set if the query fails.
    """
    try:
        response = ec2.describe_instance_type_offerings(
            LocationType="availability-zone",
            Filters=[{"Name": "instance-type", "Values": [instance_type]}],
        )
        return {offering["Location"] for offering in response.get("InstanceTypeOfferings", [])}
    except ClientError as e:
        print(f"Warning: Could not get AZ offerings: {e}", file=sys.stderr)
        return set()


def get_default_vpc_and_subnets(
    ec2: Any,
    instance_type: str,
) -> tuple[str, list[str]]:
    """Get default VPC and subnets in AZs that support the instance type.

    Subnets in supported AZs are prioritized at the front of the list,
    with unsupported AZ subnets appended as fallbacks.

    Args:
        ec2: Boto3 EC2 client.
        instance_type: EC2 instance type (used to filter AZs).

    Returns:
        Tuple of (vpc_id, subnet_id_list).

    Raises:
        RuntimeError: If no default VPC or subnets are found.
    """
    vpcs = ec2.describe_vpcs(Filters=[{"Name": "is-default", "Values": ["true"]}])
    if not vpcs["Vpcs"]:
        raise RuntimeError("No default VPC found. Please specify --vpc-id and --subnet-id")

    vpc_id = vpcs["Vpcs"][0]["VpcId"]
    supported_azs = get_supported_azs(ec2, instance_type)

    subnets = ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])
    if not subnets["Subnets"]:
        raise RuntimeError("No subnets found in default VPC")

    # Prioritize subnets in supported AZs
    subnet_list: list[str] = []
    for subnet in subnets["Subnets"]:
        az = subnet["AvailabilityZone"]
        subnet_id = subnet["SubnetId"]
        if not supported_azs or az in supported_azs:
            subnet_list.insert(0, subnet_id)
        else:
            subnet_list.append(subnet_id)

    if not subnet_list:
        raise RuntimeError("No subnets found in default VPC")

    return vpc_id, subnet_list


def create_key_pair(
    ec2: Any,
    key_name: str,
    key_dir: str | Path | None = None,
) -> str:
    """Create EC2 key pair and save the private key to a file.

    If a key pair with the same name already exists and the local file is
    present, returns the existing file path. If the key exists but the file
    is missing, deletes and recreates the key pair.

    Args:
        ec2: Boto3 EC2 client.
        key_name: Name for the EC2 key pair.
        key_dir: Directory to store the .pem file.
            Defaults to /tmp.

    Returns:
        Path to the .pem key file.

    Raises:
        RuntimeError: If key pair creation fails.
    """
    if key_dir is None:
        key_dir = Path("/tmp")
    else:
        key_dir = Path(key_dir)

    key_path = key_dir / f"{key_name}.pem"

    # Check if key already exists
    try:
        ec2.describe_key_pairs(KeyNames=[key_name])
        # Key exists -- if we have the file locally, reuse it
        if key_path.exists():
            return str(key_path)
        # Key exists but no local file -- delete and recreate
        ec2.delete_key_pair(KeyName=key_name)
    except ClientError as e:
        if e.response["Error"]["Code"] != "InvalidKeyPair.NotFound":
            raise

    # Create new key pair
    try:
        response = ec2.create_key_pair(KeyName=key_name)
    except ClientError as e:
        raise RuntimeError(f"Failed to create key pair '{key_name}': {e}") from e

    key_dir.mkdir(parents=True, exist_ok=True)
    key_path.write_text(response["KeyMaterial"])
    key_path.chmod(0o400)
    print(f"Created key pair: {key_name}", file=sys.stderr)

    return str(key_path)


def create_security_group(
    ec2: Any,
    vpc_id: str,
    name: str,
    description: str = "ISV validation security group",
) -> str:
    """Create a security group allowing SSH ingress, or return existing one.

    If a security group with the same name already exists in the VPC,
    returns its ID instead of raising an error.

    Args:
        ec2: Boto3 EC2 client.
        vpc_id: VPC to create the security group in.
        name: Security group name.
        description: Security group description.

    Returns:
        Security group ID.

    Raises:
        ClientError: For AWS API errors other than duplicate group.
    """
    try:
        response = ec2.create_security_group(
            GroupName=name,
            Description=description,
            VpcId=vpc_id,
        )
        sg_id = response["GroupId"]

        # Allow SSH from anywhere (for testing)
        ec2.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 22,
                    "ToPort": 22,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "SSH"}],
                }
            ],
        )
        print(f"Created security group: {sg_id}", file=sys.stderr)
        return sg_id
    except ClientError as e:
        if e.response["Error"]["Code"] == "InvalidGroup.Duplicate":
            sgs = ec2.describe_security_groups(
                Filters=[
                    {"Name": "group-name", "Values": [name]},
                    {"Name": "vpc-id", "Values": [vpc_id]},
                ]
            )
            if sgs["SecurityGroups"]:
                return sgs["SecurityGroups"][0]["GroupId"]
        raise


def get_architecture_for_instance_type(instance_type: str) -> str:
    """Detect CPU architecture from EC2 instance type.

    Args:
        instance_type: EC2 instance type (e.g., "g5.xlarge", "g5g.xlarge").

    Returns:
        "arm64" for Graviton instances, "x86_64" otherwise.
    """
    family = instance_type.split(".")[0] if "." in instance_type else instance_type

    # Known Graviton GPU instance families
    arm64_families = {"g5g"}

    if family in arm64_families:
        return "arm64"

    # General Graviton detection: ends with 'g' after a digit
    # e.g., c7g, m7g, r7g, t4g -- but NOT g4dn, g5, p4d (x86 GPU instances)
    if len(family) >= 2 and family[-1] == "g" and family[-2].isdigit():
        if not family.startswith(("g", "p")):
            return "arm64"

    return "x86_64"
