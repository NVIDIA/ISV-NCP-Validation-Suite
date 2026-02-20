#!/usr/bin/env python3
"""Launch a GPU virtual machine instance.

Template stub for ISV NCP Validation. Replace the TODO section with your
platform's API calls to provision a GPU-enabled VM instance.

This script must:
  1. Create an SSH key pair (or use an existing one)
  2. Create a security group allowing SSH (port 22) inbound
  3. Launch a GPU instance with the specified type
  4. Wait until the instance is in "running" state
  5. Retrieve the public IP address

Required JSON output fields:
  success           (bool)   - whether the operation succeeded
  platform          (str)    - always "vm"
  instance_id       (str)    - unique identifier for the instance
  public_ip         (str)    - public IP address of the instance
  key_file          (str)    - path to the SSH private key file
  vpc_id            (str)    - network/VPC identifier
  instance_state    (str)    - must be "running" on success
  security_group_id (str)    - security group/firewall rule identifier
  key_name          (str)    - name of the SSH key pair

Usage:
    python launch_instance.py --name isv-test-gpu --instance-type g5.xlarge --region us-west-2

Reference implementation (AWS):
    ../../../stubs/aws/vm/launch_instance.py
"""

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch GPU VM instance")
    parser.add_argument("--name", default="isv-test-gpu", help="Instance name tag")
    parser.add_argument("--instance-type", default="g5.xlarge", help="GPU instance type")
    parser.add_argument("--region", default="us-west-2", help="Cloud region")
    _args = parser.parse_args()

    result = {
        "success": False,
        "platform": "vm",
        "instance_id": None,
        "public_ip": None,
        "key_file": None,
        "vpc_id": None,
        "instance_state": None,
        "security_group_id": None,
        "key_name": None,
    }

    try:
        # ╔══════════════════════════════════════════════════════════════╗
        # ║  TODO: Replace this block with your platform's API calls     ║
        # ║                                                              ║
        # ║  1. Create or import an SSH key pair                         ║
        # ║     key_name, key_file = create_key_pair(args.name)          ║
        # ║                                                              ║
        # ║  2. Create a security group allowing SSH (port 22)           ║
        # ║     sg_id = create_security_group(vpc_id, args.name)         ║
        # ║                                                              ║
        # ║  3. Launch a GPU instance                                    ║
        # ║     instance_id = launch_instance(                           ║
        # ║         name=args.name,                                      ║
        # ║         instance_type=args.instance_type,                    ║
        # ║         region=args.region,                                  ║
        # ║         key_name=key_name,                                   ║
        # ║         security_group_id=sg_id,                             ║
        # ║     )                                                        ║
        # ║                                                              ║
        # ║  4. Wait for the instance to reach "running" state           ║
        # ║     wait_for_running(instance_id)                            ║
        # ║                                                              ║
        # ║  5. Retrieve the public IP address                           ║
        # ║     public_ip = get_public_ip(instance_id)                   ║
        # ║                                                              ║
        # ║  6. Populate the result dict:                                ║
        # ║     result["instance_id"] = instance_id                      ║
        # ║     result["public_ip"] = public_ip                          ║
        # ║     result["key_file"] = key_file                            ║
        # ║     result["vpc_id"] = vpc_id                                ║
        # ║     result["instance_state"] = "running"                     ║
        # ║     result["security_group_id"] = sg_id                      ║
        # ║     result["key_name"] = key_name                            ║
        # ║     result["success"] = True                                 ║
        # ╚══════════════════════════════════════════════════════════════╝

        result["error"] = "Not implemented - replace with your platform's VM launch logic"

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
