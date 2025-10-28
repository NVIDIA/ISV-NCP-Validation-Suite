#!/usr/bin/env python3
"""Launch AWS EC2 GPU instance for VM testing.

Usage:
    python launch_instance.py --name test-gpu --instance-type g5.xlarge --region us-west-2

Output JSON:
{
    "success": true,
    "instance_id": "i-xxx",
    "instance_type": "g5.xlarge",
    "public_ip": "54.x.x.x",
    "private_ip": "10.0.1.5",
    "state": "running",
    "ami_id": "ami-xxx",
    "key_name": "isv-test-key",
    "key_file": "/tmp/isv-test-key.pem"
}
"""

import argparse
import json
import os
import sys
from typing import Any

import boto3
from botocore.exceptions import ClientError


def get_architecture_for_instance_type(instance_type: str) -> str:
    """Detect CPU architecture from instance type.

    Args:
        instance_type: EC2 instance type (e.g., "g5.xlarge", "g5g.xlarge")

    Returns:
        "arm64" for Graviton instances, "x86_64" otherwise
    """
    # Extract instance family (e.g., "g5g" from "g5g.xlarge")
    family = instance_type.split(".")[0] if "." in instance_type else instance_type

    # Graviton (ARM64) GPU instance families end with 'g' after the generation number
    # Examples: g5g (Graviton2 + T4G GPU), c7g, m7g, r7g (non-GPU Graviton)
    # Non-Graviton GPU: g4dn, g5, p3, p4, p5, p4d, p5
    arm64_patterns = [
        "g5g",  # Graviton2 with NVIDIA T4G
        # Add more Graviton GPU families as they become available
    ]

    # Also check for general Graviton patterns (family ends with 'g' after number)
    # e.g., c7g, m7g, r7g, t4g, but NOT g4dn, g5 (these are x86 GPU instances)
    if family in arm64_patterns:
        return "arm64"

    # General Graviton detection: ends with 'g' and has a number before it
    # This catches c7g, m7g, r7g, t4g, etc. but not g4dn, g5, p4d
    if len(family) >= 2 and family[-1] == "g" and family[-2].isdigit():
        # But exclude GPU families that start with 'g' or 'p' (those are x86 GPU)
        if not family.startswith(("g", "p")):
            return "arm64"

    return "x86_64"


def get_gpu_ami(ec2: Any, instance_type: str) -> str | None:
    """Get appropriate AMI for GPU instance with NVIDIA drivers pre-installed.

    Selects AMI based on instance type architecture (x86_64 vs arm64).

    Args:
        ec2: boto3 EC2 client
        instance_type: EC2 instance type (used to detect architecture)

    Returns:
        AMI ID or None if not found
    """
    architecture = get_architecture_for_instance_type(instance_type)

    # AMI search patterns by architecture
    if architecture == "arm64":
        # ARM64/Graviton GPU AMIs
        ami_patterns = [
            "Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 22.04)*",
            "Deep Learning AMI Graviton GPU PyTorch*Ubuntu 22.04*",
            "Deep Learning Base AMI GPU Graviton*Ubuntu 22.04*",
        ]
        fallback_pattern = "ubuntu/images/hvm-ssd-gp3/ubuntu-jammy-22.04-arm64-server-*"
    else:
        # x86_64 GPU AMIs (Intel/AMD)
        ami_patterns = [
            "Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 22.04)*",
            "Deep Learning Base GPU AMI (Ubuntu 22.04)*",
            "Deep Learning AMI GPU PyTorch*Ubuntu 22.04*",
            "Deep Learning AMI GPU PyTorch*Ubuntu 20.04*",
            "Deep Learning Base AMI (Ubuntu 20.04)*",
        ]
        fallback_pattern = "ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"

    # Search for Deep Learning AMIs
    for pattern in ami_patterns:
        response = ec2.describe_images(
            Owners=["amazon"],
            Filters=[
                {"Name": "name", "Values": [pattern]},
                {"Name": "state", "Values": ["available"]},
                {"Name": "architecture", "Values": [architecture]},
            ],
        )
        images = sorted(response["Images"], key=lambda x: x["CreationDate"], reverse=True)
        if images:
            return images[0]["ImageId"]

    # Last resort: plain Ubuntu (will NOT have GPU drivers)
    response = ec2.describe_images(
        Owners=["amazon"],
        Filters=[
            {"Name": "name", "Values": [fallback_pattern]},
            {"Name": "state", "Values": ["available"]},
        ],
    )
    images = sorted(response["Images"], key=lambda x: x["CreationDate"], reverse=True)
    return images[0]["ImageId"] if images else None


def create_key_pair(ec2: Any, key_name: str) -> str | None:
    """Create EC2 key pair and return path to key file."""
    key_file = f"/tmp/{key_name}.pem"

    # Check if key already exists
    try:
        ec2.describe_key_pairs(KeyNames=[key_name])
        # Key exists, check if we have the file
        if os.path.exists(key_file):
            return key_file
        # Key exists but no file - delete and recreate
        ec2.delete_key_pair(KeyName=key_name)
    except ClientError as e:
        if e.response["Error"]["Code"] != "InvalidKeyPair.NotFound":
            raise

    # Create new key pair
    response = ec2.create_key_pair(KeyName=key_name)
    key_material = response["KeyMaterial"]

    with open(key_file, "w") as f:
        f.write(key_material)
    os.chmod(key_file, 0o400)

    return key_file


def create_security_group(ec2: Any, vpc_id: str, name: str) -> str:
    """Create security group allowing SSH."""
    try:
        response = ec2.create_security_group(
            GroupName=name,
            Description="ISV Test VM Security Group",
            VpcId=vpc_id,
        )
        sg_id = response["GroupId"]

        # Allow SSH from anywhere
        ec2.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 22,
                    "ToPort": 22,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                }
            ],
        )
        return sg_id
    except ClientError as e:
        if e.response["Error"]["Code"] == "InvalidGroup.Duplicate":
            # Get existing group
            sgs = ec2.describe_security_groups(
                Filters=[
                    {"Name": "group-name", "Values": [name]},
                    {"Name": "vpc-id", "Values": [vpc_id]},
                ]
            )
            return sgs["SecurityGroups"][0]["GroupId"]
        raise


def get_supported_azs(ec2: Any, instance_type: str) -> set[str]:
    """Get availability zones that support the instance type."""
    try:
        response = ec2.describe_instance_type_offerings(
            LocationType="availability-zone",
            Filters=[{"Name": "instance-type", "Values": [instance_type]}],
        )
        return {offering["Location"] for offering in response["InstanceTypeOfferings"]}
    except ClientError:
        return set()  # If check fails, try all AZs


def get_default_vpc_and_subnets(ec2: Any, instance_type: str) -> tuple[str, list[str]]:
    """Get default VPC and subnets in AZs that support the instance type."""
    vpcs = ec2.describe_vpcs(Filters=[{"Name": "is-default", "Values": ["true"]}])
    if not vpcs["Vpcs"]:
        raise RuntimeError("No default VPC found. Please specify --vpc-id and --subnet-id")

    vpc_id = vpcs["Vpcs"][0]["VpcId"]

    # Get AZs that support the instance type
    supported_azs = get_supported_azs(ec2, instance_type)

    subnets = ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])
    if not subnets["Subnets"]:
        raise RuntimeError("No subnets found in default VPC")

    # Filter subnets to supported AZs, prioritizing them
    subnet_list = []
    for subnet in subnets["Subnets"]:
        az = subnet["AvailabilityZone"]
        subnet_id = subnet["SubnetId"]
        if not supported_azs or az in supported_azs:
            subnet_list.insert(0, subnet_id)  # Prioritize supported AZs
        else:
            subnet_list.append(subnet_id)  # Add unsupported at end as fallback

    if not subnet_list:
        raise RuntimeError("No subnets found in default VPC")

    return vpc_id, subnet_list


def main() -> int:
    """Launch a GPU-enabled EC2 instance for VM testing.

    Parses command-line arguments, creates necessary resources (key pair,
    security group), selects an appropriate AMI based on instance type
    architecture, and launches the instance with fallback subnet logic.

    Returns:
        0 on success, 1 on failure
    """
    parser = argparse.ArgumentParser(description="Launch GPU instance")
    parser.add_argument("--name", default="isv-test-gpu", help="Instance name")
    parser.add_argument("--instance-type", default="g5.xlarge", help="EC2 instance type")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-west-2"))
    parser.add_argument("--vpc-id", help="VPC ID (uses default if not specified)")
    parser.add_argument("--subnet-id", help="Subnet ID (uses first subnet if not specified)")
    parser.add_argument("--ami-id", help="AMI ID (auto-detects GPU AMI if not specified)")
    parser.add_argument("--key-name", default="isv-test-key", help="EC2 key pair name")
    args = parser.parse_args()

    ec2 = boto3.client("ec2", region_name=args.region)

    result = {
        "success": False,
        "platform": "vm",
        "instance_id": None,
        "instance_type": args.instance_type,
        "region": args.region,
    }

    try:
        # Get VPC and subnets
        if args.vpc_id and args.subnet_id:
            vpc_id = args.vpc_id
            subnet_list = [args.subnet_id]
        else:
            vpc_id, subnet_list = get_default_vpc_and_subnets(ec2, args.instance_type)

        # Create key pair
        key_file = create_key_pair(ec2, args.key_name)
        result["key_name"] = args.key_name
        result["key_file"] = key_file

        # Create security group
        sg_name = f"{args.name}-sg"
        sg_id = create_security_group(ec2, vpc_id, sg_name)
        result["security_group_id"] = sg_id

        # Get AMI (architecture-aware selection based on instance type)
        architecture = get_architecture_for_instance_type(args.instance_type)
        result["architecture"] = architecture

        ami_id = args.ami_id or get_gpu_ami(ec2, args.instance_type)
        if not ami_id:
            raise RuntimeError(f"Could not find suitable {architecture} AMI")
        result["ami_id"] = ami_id

        # Get AMI name for logging
        ami_info = ec2.describe_images(ImageIds=[ami_id])
        if ami_info["Images"]:
            result["ami_name"] = ami_info["Images"][0].get("Name", "unknown")
            result["ami_architecture"] = ami_info["Images"][0].get("Architecture", "unknown")

        # Try launching in each subnet until one succeeds
        last_error = None
        instance_id = None

        for subnet_id in subnet_list:
            try:
                response = ec2.run_instances(
                    ImageId=ami_id,
                    InstanceType=args.instance_type,
                    MinCount=1,
                    MaxCount=1,
                    KeyName=args.key_name,
                    SubnetId=subnet_id,
                    SecurityGroupIds=[sg_id],
                    TagSpecifications=[
                        {
                            "ResourceType": "instance",
                            "Tags": [{"Key": "Name", "Value": args.name}],
                        }
                    ],
                    BlockDeviceMappings=[
                        {
                            "DeviceName": "/dev/sda1",
                            "Ebs": {"VolumeSize": 100, "VolumeType": "gp3"},
                        }
                    ],
                )
                instance_id = response["Instances"][0]["InstanceId"]
                result["subnet_id"] = subnet_id
                break  # Success, exit loop
            except ClientError as e:
                error_code = e.response["Error"]["Code"]
                if error_code == "Unsupported":
                    # AZ doesn't support instance type, try next subnet
                    last_error = e
                    continue
                raise  # Other errors should be raised

        if not instance_id:
            if last_error:
                raise last_error
            raise RuntimeError("Failed to launch instance in any subnet")

        result["instance_id"] = instance_id

        # Wait for instance to be running
        waiter = ec2.get_waiter("instance_running")
        waiter.wait(InstanceIds=[instance_id])

        # Wait for instance status checks to pass (ensures OS is ready)
        status_waiter = ec2.get_waiter("instance_status_ok")
        status_waiter.wait(InstanceIds=[instance_id])

        # Get instance details
        instances = ec2.describe_instances(InstanceIds=[instance_id])
        instance = instances["Reservations"][0]["Instances"][0]

        result["public_ip"] = instance.get("PublicIpAddress")
        result["private_ip"] = instance.get("PrivateIpAddress")
        result["state"] = instance["State"]["Name"]
        result["vpc_id"] = vpc_id
        result["availability_zone"] = instance.get("Placement", {}).get("AvailabilityZone")
        result["success"] = True

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
