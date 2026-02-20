#!/usr/bin/env python3
"""Deploy a NIM inference container on a remote GPU host via SSH.

Template stub for ISV NCP Validation. Replace the TODO section with your
platform's logic to pull and start a NIM container on a remote host.

This script must:
  1. SSH into the remote host
  2. Authenticate with the NGC container registry
  3. Pull the NIM container image
  4. Start the container with GPU access
  5. Wait for the health endpoint to report ready

Requires the NGC_NIM_API_KEY environment variable to be set.

Required JSON output fields:
  success          (bool)  - whether the operation succeeded
  platform         (str)   - always "nim"
  host             (str)   - remote host IP/hostname
  container_id     (str)   - running container ID
  health_endpoint  (str)   - URL of the NIM health endpoint
  model_name       (str)   - name of the deployed NIM model

Usage:
    NGC_NIM_API_KEY=nvapi-... python deploy_nim.py \\
        --host 54.1.2.3 --key-file /tmp/key.pem

Reference implementation (AWS):
    ../../../stubs/common/deploy_nim.py
    (see also: AWS VM config usage in ../../../aws-vm.yaml)
"""

import argparse
import json
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy NIM container on remote host")
    parser.add_argument("--host", required=True, help="Remote host IP/hostname")
    parser.add_argument("--key-file", required=True, help="SSH private key path")
    args = parser.parse_args()

    ngc_api_key = os.environ.get("NGC_NIM_API_KEY", "")

    result = {
        "success": False,
        "platform": "nim",
        "host": args.host,
        "container_id": None,
        "health_endpoint": None,
        "model_name": None,
    }

    if not ngc_api_key:
        result["success"] = True
        result["skipped"] = True
        result["skip_reason"] = "NGC_NIM_API_KEY not set"
        print(json.dumps(result, indent=2))
        return 0

    try:
        # ╔══════════════════════════════════════════════════════════════╗
        # ║  TODO: Replace this block with your deployment logic         ║
        # ║                                                              ║
        # ║  1. SSH into the remote host                                 ║
        # ║     ssh = connect(args.host, key_file=args.key_file)         ║
        # ║                                                              ║
        # ║  2. Log in to the NGC container registry                     ║
        # ║     ssh.run("docker login nvcr.io -u '$oauthtoken' ...")     ║
        # ║                                                              ║
        # ║  3. Pull the NIM container image                             ║
        # ║     image = "nvcr.io/nim/meta/llama-3.2-1b-instruct"         ║
        # ║     ssh.run(f"docker pull {image}")                          ║
        # ║                                                              ║
        # ║  4. Start the container with GPU access                      ║
        # ║     ssh.run("docker run -d --gpus all "                      ║
        # ║             f"--name isv-nim -p 8000:8000 "                  ║
        # ║             f"-e NGC_API_KEY={ngc_api_key} {image}")         ║
        # ║                                                              ║
        # ║  5. Wait for the health endpoint to report ready             ║
        # ║     poll until: curl http://localhost:8000/v1/health/ready   ║
        # ║                                                              ║
        # ║  6. Populate result                                          ║
        # ║     result["container_id"] = container_id                    ║
        # ║     result["health_endpoint"] = "http://localhost:8000"      ║
        # ║     result["model_name"] = "meta/llama-3.2-1b-instruct"      ║
        # ║     result["success"] = True                                 ║
        # ╚══════════════════════════════════════════════════════════════╝

        result["error"] = "Not implemented - replace with your platform's NIM deployment logic"

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
