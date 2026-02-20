#!/usr/bin/env python3
"""Tear down all resources created during ISO validation.

Provider-agnostic template — replace the TODO section with your platform's
resource cleanup calls. Each resource should be deleted independently so
partial cleanup succeeds even if some deletions fail.

Required JSON output:
{
    "success":           bool      — true if all resources deleted,
    "platform":          str       — "iso",
    "resources_deleted": list[str] — names/IDs of deleted resources,
    "message":           str       — human-readable summary
}

Usage:
    python teardown.py --instance-id i-xxx --ami-id ami-xxx --snapshot-ids snap-a,snap-b \\
        --bucket-name my-bucket --key-name my-key --security-group-id sg-xxx \\
        --instance-profile my-profile --region us-west-2

    Pass --skip-destroy to skip actual deletion (dry-run).

AWS reference implementation:
    ../../../stubs/aws/iso/teardown.py
"""

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Tear down ISO validation resources")
    parser.add_argument("--instance-id", default="", help="Instance to terminate")
    parser.add_argument("--ami-id", default="", help="Machine image to deregister")
    parser.add_argument("--snapshot-ids", default="", help="Comma-separated snapshot/disk IDs to delete")
    parser.add_argument("--bucket-name", default="", help="Storage bucket to delete")
    parser.add_argument("--key-name", default="", help="Key pair to delete")
    parser.add_argument("--security-group-id", default="", help="Security group to delete")
    parser.add_argument("--instance-profile", default="", help="Instance profile to delete")
    parser.add_argument("--region", required=True, help="Cloud region / availability zone")
    parser.add_argument("--skip-destroy", action="store_true", help="Skip actual deletion (dry-run)")
    args = parser.parse_args()

    result: dict = {
        "success": False,
        "platform": "iso",
        "resources_deleted": [],
        "message": "",
    }

    if args.skip_destroy:
        result["success"] = True
        result["message"] = "Teardown skipped (--skip-destroy)"
        print(json.dumps(result, indent=2))
        return 0

    _snapshot_ids = [s.strip() for s in args.snapshot_ids.split(",") if s.strip()]

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  TODO: Replace this block with your platform's implementation    ║
    # ║                                                                  ║
    # ║  Delete each resource, appending to resources_deleted:           ║
    # ║                                                                  ║
    # ║  1. Terminate the instance (args.instance_id)                    ║
    # ║     → result["resources_deleted"].append("instance:<id>")        ║
    # ║  2. Deregister / delete the machine image (args.ami_id)          ║
    # ║     → result["resources_deleted"].append("image:<id>")           ║
    # ║  3. Delete snapshots / disks (snapshot_ids)                      ║
    # ║     → result["resources_deleted"].append("snapshot:<id>")        ║
    # ║  4. Delete the storage bucket (args.bucket_name)                 ║
    # ║     → result["resources_deleted"].append("bucket:<name>")        ║
    # ║  5. Delete the key pair (args.key_name)                          ║
    # ║     → result["resources_deleted"].append("keypair:<name>")       ║
    # ║  6. Delete the security group (args.security_group_id)           ║
    # ║     → result["resources_deleted"].append("sg:<id>")              ║
    # ║  7. Delete the instance profile (args.instance_profile)          ║
    # ║     → result["resources_deleted"].append("profile:<name>")       ║
    # ║  8. Set result["message"] and result["success"] = True           ║
    # ╚══════════════════════════════════════════════════════════════════╝

    result["error"] = "Not implemented - replace with your platform's resource teardown logic"

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
