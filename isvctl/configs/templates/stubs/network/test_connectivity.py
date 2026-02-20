#!/usr/bin/env python3
"""Network connectivity test - TEMPLATE (replace with your platform implementation).

This script is called during the "test" phase. It uses the SHARED VPC
created by create_vpc.py (passed via Jinja2 template variables):
  1. Launch instances in the provided subnets
  2. Verify each instance was assigned to the correct network / subnet
  3. Test connectivity between instances
  4. Clean up launched instances
  5. Print a JSON object to stdout

Required JSON output fields:
  {
    "success": true,                           # boolean - did connectivity check pass?
    "platform": "network",                     # string  - always "network"
    "test_name": "connectivity",               # string  - always "connectivity"
    "instances": [                             # list    - launched instance details
      {"instance_id": "i-abc", "subnet_id": "subnet-abc", "private_ip": "10.0.1.5"}
    ],
    "connectivity_verified": true              # boolean - instances can communicate?
  }

On failure, set "success": false and include an "error" field.

Usage:
    python test_connectivity.py --vpc-id vpc-abc123 \\
        --subnet-ids subnet-abc,subnet-def --sg-id sg-abc123 --region us-west-2

Reference implementation: ../../../stubs/aws/network/test_connectivity.py
"""

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Network connectivity test (template)")
    parser.add_argument("--vpc-id", required=True, help="VPC / network ID to test in")
    parser.add_argument("--subnet-ids", required=True, help="Comma-separated subnet IDs")
    parser.add_argument("--sg-id", required=True, help="Security group ID")
    parser.add_argument("--region", default="us-west-2", help="Cloud region")
    args = parser.parse_args()

    _subnet_ids = [s.strip() for s in args.subnet_ids.split(",") if s.strip()]

    result: dict = {
        "success": False,
        "platform": "network",
        "test_name": "connectivity",
        "instances": [],
        "connectivity_verified": False,
    }

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  TODO: Replace this block with your platform's connectivity      ║
    # ║        test                                                      ║
    # ║                                                                  ║
    # ║  Example (pseudocode):                                           ║
    # ║    client = MyCloudClient(region=args.region)                    ║
    # ║                                                                  ║
    # ║    # Launch one instance per subnet                              ║
    # ║    instances = []                                                ║
    # ║    for sid in subnet_ids:                                        ║
    # ║        inst = client.launch_instance(                            ║
    # ║            subnet_id=sid,                                        ║
    # ║            security_group=args.sg_id,                            ║
    # ║        )                                                         ║
    # ║        instances.append(inst)                                    ║
    # ║        result["instances"].append({                              ║
    # ║            "instance_id": inst.id,                               ║
    # ║            "subnet_id": sid,                                     ║
    # ║            "private_ip": inst.private_ip,                        ║
    # ║        })                                                        ║
    # ║                                                                  ║
    # ║    # Verify connectivity between instances                       ║
    # ║    for a, b in combinations(instances, 2):                       ║
    # ║        assert client.test_connectivity(a.id, b.private_ip)       ║
    # ║    result["connectivity_verified"] = True                        ║
    # ║                                                                  ║
    # ║    # Cleanup instances (VPC remains for other tests)             ║
    # ║    for inst in instances:                                        ║
    # ║        client.terminate_instance(inst.id)                        ║
    # ║    result["success"] = True                                      ║
    # ╚══════════════════════════════════════════════════════════════════╝

    result["error"] = "Not implemented - replace with your platform's connectivity test logic"
    print(json.dumps(result, indent=2))

    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
