#!/usr/bin/env python3
"""Tear down a NIM inference container on a remote host via SSH.

Template stub for ISV NCP Validation. Replace the TODO section with your
platform's logic to stop and remove the NIM container.

This script must:
  1. SSH into the remote host
  2. Stop the running NIM container
  3. Remove the container

Required JSON output fields:
  success   (bool)           - whether the operation succeeded
  platform  (str)            - always "nim"
  host      (str)            - remote host IP/hostname
  message   (str)            - human-readable summary of the teardown
  error     (str, optional)  - error message or details provided when the operation fails

Usage:
    python teardown_nim.py --host 54.1.2.3 --key-file /tmp/key.pem

Reference implementation (AWS):
    ../../../stubs/aws/common/teardown_nim.py
    (see also: AWS VM config usage in ../../../aws/vm.yaml)
"""

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Tear down NIM container on remote host")
    parser.add_argument("--host", required=True, help="Remote host IP/hostname")
    parser.add_argument("--key-file", required=True, help="SSH private key path")
    args = parser.parse_args()

    result = {
        "success": False,
        "platform": "nim",
        "host": args.host,
        "message": "",
    }

    try:
        # ╔══════════════════════════════════════════════════════════════╗
        # ║  TODO: Replace this block with your teardown logic           ║
        # ║                                                              ║
        # ║  1. SSH into the remote host                                 ║
        # ║     ssh = connect(args.host, key_file=args.key_file)         ║
        # ║                                                              ║
        # ║  2. Stop the NIM container                                   ║
        # ║     ssh.run("docker stop isv-nim")                           ║
        # ║                                                              ║
        # ║  3. Remove the container                                     ║
        # ║     ssh.run("docker rm isv-nim")                             ║
        # ║                                                              ║
        # ║  4. Populate result                                          ║
        # ║     result["message"] = "NIM container removed"              ║
        # ║     result["success"] = True                                 ║
        # ╚══════════════════════════════════════════════════════════════╝

        result["error"] = "Not implemented - replace with your platform's NIM teardown logic"

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
