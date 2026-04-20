#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Teardown bare-metal instance and resources - TEMPLATE (replace with your platform implementation).

This script is called during the "teardown" phase. It must:
  1. Check if --skip-destroy is set (or BM_SKIP_TEARDOWN env var); if so, skip
  2. Terminate the bare-metal instance (longer wait than VM for full shutdown)
  3. Optionally delete the key pair (if --delete-key-pair is set)
  4. Optionally delete the security group (if --delete-security-group is set)
  5. Print a JSON object to stdout

Required JSON output fields:
  {
    "success": true,                              # boolean - did teardown succeed?
    "platform": "bm",                             # string  - always "bm"
    "resources_deleted": ["instance:i-xxx", ...], # list    - what was cleaned up
    "message": "Teardown completed"               # string  - human-readable status
  }

On failure, set "success": false and include an "error" field.
If resources don't exist, return success (idempotent teardown).

Usage:
    python teardown.py --instance-id <id> --region <region> --delete-key-pair --delete-security-group
    python teardown.py --instance-id <id> --region <region> --skip-destroy

    # Also supports env var:
    BM_SKIP_TEARDOWN=true python teardown.py --instance-id <id> --region <region>

Reference implementation: ../../aws/bare_metal/teardown.py
"""

import argparse
import json
import os
import sys

# ISVCTL_DEMO_MODE=1 enables demo-success output (used by `make smoke-test`).
DEMO_MODE = os.environ.get("ISVCTL_DEMO_MODE") == "1"


def main() -> int:
    """Teardown bare-metal instance and associated resources, emitting JSON result."""
    parser = argparse.ArgumentParser(description="Teardown bare-metal instance (template)")
    parser.add_argument("--instance-id", required=True, help="Instance identifier")
    parser.add_argument("--region", required=True, help="Cloud region")
    parser.add_argument("--delete-key-pair", action="store_true", help="Also delete key pair")
    parser.add_argument("--delete-security-group", action="store_true", help="Also delete security group")
    parser.add_argument("--skip-destroy", action="store_true", help="Skip actual destruction")
    args = parser.parse_args()

    result: dict = {
        "success": False,
        "platform": "bm",
        "resources_deleted": [],
        "message": "",
    }

    # Support env var override for skip-destroy
    if args.skip_destroy or os.environ.get("BM_SKIP_TEARDOWN") == "true":
        result["success"] = True
        result["message"] = (
            f"Teardown skipped. Instance {args.instance_id} is still running. "
            f"To teardown later, unset BM_SKIP_TEARDOWN and rerun."
        )
        print(json.dumps(result, indent=2))
        return 0

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  TODO: Replace this block with your platform's teardown logic    ║
    # ║                                                                  ║
    # ║  Example (pseudocode):                                           ║
    # ║    client = MyCloudClient(region=args.region)                    ║
    # ║                                                                  ║
    # ║    1. Terminate bare-metal instance (longer wait for BM):        ║
    # ║       client.terminate_instance(args.instance_id)                ║
    # ║       client.wait_until_terminated(                              ║
    # ║           args.instance_id, timeout=1800                         ║
    # ║       )                                                          ║
    # ║       result["resources_deleted"].append(                        ║
    # ║           f"instance:{args.instance_id}"                         ║
    # ║       )                                                          ║
    # ║                                                                  ║
    # ║    2. Delete key pair (if --delete-key-pair):                    ║
    # ║       if args.delete_key_pair:                                   ║
    # ║           client.delete_key_pair(key_name)                       ║
    # ║           result["resources_deleted"].append(f"key:{key_name}")  ║
    # ║                                                                  ║
    # ║    3. Delete security group (if --delete-security-group):        ║
    # ║       if args.delete_security_group:                             ║
    # ║           client.delete_security_group(sg_id)                    ║
    # ║           result["resources_deleted"].append(f"sg:{sg_id}")      ║
    # ║                                                                  ║
    # ║    result["success"] = True                                      ║
    # ║    result["message"] = "Bare-metal instance teardown completed"  ║
    # ╚══════════════════════════════════════════════════════════════════╝

    if DEMO_MODE:
        result["resources_deleted"].append(f"instance:{args.instance_id}")
        if args.delete_key_pair:
            result["resources_deleted"].append("key_pair:dummy-bm-key")
        if args.delete_security_group:
            result["resources_deleted"].append("security_group:dummy-sg-bm-0001")
        result["message"] = "Bare-metal instance and associated resources deleted"
        result["success"] = True
    else:
        result["error"] = "Not implemented - replace with your platform's instance teardown logic"

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
