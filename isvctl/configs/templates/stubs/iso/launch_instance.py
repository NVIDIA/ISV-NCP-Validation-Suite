#!/usr/bin/env python3
"""Launch a GPU instance from an imported machine image.

Provider-agnostic template — replace the TODO section with your platform's
compute instance creation calls.

Required JSON output:
{
    "success":           bool — true if instance is running,
    "platform":          str  — "iso",
    "instance_id":       str  — unique instance identifier,
    "public_ip":         str  — public IP address for SSH,
    "key_path":          str  — local path to the SSH private key,
    "instance_state":    str  — "running",
    "key_name":          str  — name of the key pair,
    "security_group_id": str  — security group / firewall rule ID,
    "instance_profile":  str  — IAM / instance profile name,
    "error":             str  — (optional) error message, present when success is false
}

Usage:
    python launch_instance.py --image-id <image-id> --instance-type g4dn.xlarge --region us-west-2

AWS reference implementation:
    ../../../stubs/aws/iso/launch_instance.py
"""

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch GPU instance from imported image")
    parser.add_argument("--image-id", required=True, help="Imported machine image ID")
    parser.add_argument("--instance-type", required=True, help="Instance type / flavor (e.g. g4dn.xlarge)")
    parser.add_argument("--region", required=True, help="Cloud region / availability zone")
    args = parser.parse_args()  # noqa: F841 — used in TODO block below

    result: dict = {
        "success": False,
        "platform": "iso",
        "instance_id": "",
        "public_ip": "",
        "key_path": "",
        "instance_state": "",
        "key_name": "",
        "security_group_id": "",
        "instance_profile": "",
    }

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  TODO: Replace this block with your platform's implementation    ║
    # ║                                                                  ║
    # ║  1. Create an SSH key pair                                       ║
    # ║     → result["key_name"] = "<key-pair-name>"                     ║
    # ║     → result["key_path"] = "<path-to-private-key>"               ║
    # ║  2. Create a security group / firewall rule (allow SSH)          ║
    # ║     → result["security_group_id"] = "<sg-id>"                    ║
    # ║  3. (Optional) Create an instance profile / service account      ║
    # ║     → result["instance_profile"] = "<profile-name>"              ║
    # ║  4. Launch GPU instance from the imported image                  ║
    # ║     → result["instance_id"] = "<instance-id>"                    ║
    # ║  5. Wait for the instance to reach "running" state               ║
    # ║     → result["instance_state"] = "running"                       ║
    # ║  6. Get the public IP                                            ║
    # ║     → result["public_ip"] = "<ip-address>"                       ║
    # ║  7. Set result["success"] = True                                 ║
    # ╚══════════════════════════════════════════════════════════════════╝

    result["error"] = "Not implemented - replace with your platform's instance launch logic"

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
