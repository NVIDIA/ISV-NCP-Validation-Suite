#!/usr/bin/env python3
"""Teardown AWS VPC and all associated resources.

Usage:
    python teardown.py --vpc-id vpc-xxx --region us-west-2

Output JSON:
{
    "success": true,
    "resources_destroyed": true,
    "deleted": {
        "instances": ["i-xxx"],
        "security_groups": ["sg-xxx"],
        "subnets": ["subnet-xxx"],
        "route_tables": ["rtb-xxx"],
        "internet_gateways": ["igw-xxx"],
        "vpc": "vpc-xxx"
    }
}
"""

import argparse
import json
import os
import sys
import time
from typing import Any

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

import boto3
from botocore.exceptions import ClientError
from errors import handle_aws_errors


def delete_with_retry(func, resource_type: str, max_retries: int = 5, **kwargs) -> bool:
    """Delete resource with retry for dependency errors."""
    for attempt in range(max_retries):
        try:
            func(**kwargs)
            return True
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "DependencyViolation":
                if attempt < max_retries - 1:
                    time.sleep(5 * (attempt + 1))
                    continue
            elif error_code in [
                "InvalidGroup.NotFound",
                "InvalidSubnetID.NotFound",
                "InvalidRouteTableID.NotFound",
                "InvalidInternetGatewayID.NotFound",
                "InvalidVpcID.NotFound",
            ]:
                return True  # Already deleted
            raise
    return False


def teardown_vpc(ec2: Any, vpc_id: str) -> dict[str, Any]:
    """Delete VPC and all associated resources."""
    deleted = {
        "instances": [],
        "security_groups": [],
        "subnets": [],
        "route_tables": [],
        "internet_gateways": [],
        "vpc": None,
    }

    # Terminate all instances in VPC
    instances = ec2.describe_instances(
        Filters=[
            {"Name": "vpc-id", "Values": [vpc_id]},
            {"Name": "instance-state-name", "Values": ["running", "stopped", "pending"]},
        ]
    )
    instance_ids = []
    for reservation in instances["Reservations"]:
        for instance in reservation["Instances"]:
            instance_ids.append(instance["InstanceId"])

    if instance_ids:
        ec2.terminate_instances(InstanceIds=instance_ids)
        waiter = ec2.get_waiter("instance_terminated")
        waiter.wait(InstanceIds=instance_ids)
        deleted["instances"] = instance_ids

    # Delete security groups (except default)
    sgs = ec2.describe_security_groups(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])
    for sg in sgs["SecurityGroups"]:
        if sg["GroupName"] != "default":
            delete_with_retry(
                ec2.delete_security_group,
                "security_group",
                GroupId=sg["GroupId"],
            )
            deleted["security_groups"].append(sg["GroupId"])

    # Delete subnets
    subnets = ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])
    for subnet in subnets["Subnets"]:
        delete_with_retry(
            ec2.delete_subnet,
            "subnet",
            SubnetId=subnet["SubnetId"],
        )
        deleted["subnets"].append(subnet["SubnetId"])

    # Delete route tables (except main)
    rtbs = ec2.describe_route_tables(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])
    for rtb in rtbs["RouteTables"]:
        # Skip main route table
        is_main = any(assoc.get("Main", False) for assoc in rtb.get("Associations", []))
        if not is_main:
            # Delete associations first
            for assoc in rtb.get("Associations", []):
                if not assoc.get("Main", False) and assoc.get("RouteTableAssociationId"):
                    try:
                        ec2.disassociate_route_table(AssociationId=assoc["RouteTableAssociationId"])
                    except ClientError:
                        pass

            delete_with_retry(
                ec2.delete_route_table,
                "route_table",
                RouteTableId=rtb["RouteTableId"],
            )
            deleted["route_tables"].append(rtb["RouteTableId"])

    # Detach and delete internet gateways
    igws = ec2.describe_internet_gateways(Filters=[{"Name": "attachment.vpc-id", "Values": [vpc_id]}])
    for igw in igws["InternetGateways"]:
        try:
            ec2.detach_internet_gateway(
                InternetGatewayId=igw["InternetGatewayId"],
                VpcId=vpc_id,
            )
        except ClientError:
            pass

        delete_with_retry(
            ec2.delete_internet_gateway,
            "internet_gateway",
            InternetGatewayId=igw["InternetGatewayId"],
        )
        deleted["internet_gateways"].append(igw["InternetGatewayId"])

    # Delete VPC
    delete_with_retry(ec2.delete_vpc, "vpc", VpcId=vpc_id)
    deleted["vpc"] = vpc_id

    return deleted


@handle_aws_errors
def main() -> int:
    parser = argparse.ArgumentParser(description="Teardown VPC")
    parser.add_argument("--vpc-id", required=True, help="VPC ID to delete")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-west-2"))
    parser.add_argument("--skip-destroy", action="store_true", help="Skip actual destroy")
    args = parser.parse_args()

    result = {
        "success": False,
        "platform": "network",
        "resources_destroyed": False,
        "network_id": args.vpc_id,
        "deleted": {},
    }

    # Check both flag and environment variable
    skip_destroy = args.skip_destroy or os.environ.get("AWS_NETWORK_TEARDOWN_ENABLED", "").lower() != "true"
    if skip_destroy:
        result["success"] = True
        result["message"] = "Destroy skipped (set AWS_NETWORK_TEARDOWN_ENABLED=true to enable)"
        print(json.dumps(result, indent=2))
        return 0

    ec2 = boto3.client("ec2", region_name=args.region)

    try:
        deleted = teardown_vpc(ec2, args.vpc_id)
        result["deleted"] = deleted
        result["success"] = True
        result["resources_destroyed"] = True
        result["message"] = "VPC and all resources destroyed successfully"
    except ClientError as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
