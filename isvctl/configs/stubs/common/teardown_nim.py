#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Tear down a NIM inference container on a remote host via SSH.

Stops and removes the NIM container, optionally removes the image.

Usage:
    python teardown_nim.py --host 54.1.2.3 --key-file /tmp/key.pem
    python teardown_nim.py --host 54.1.2.3 --key-file /tmp/key.pem --remove-image

Output JSON:
{
    "success": true,
    "platform": "vm",
    "container_removed": true,
    "image_removed": false,
    "container_name": "isv-nim"
}

Requires: paramiko
"""

import argparse
import json
import sys
from typing import Any

import paramiko


def ssh_connect(host: str, user: str, key_file: str) -> paramiko.SSHClient:
    """Create SSH connection to remote host."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=host,
        username=user,
        key_filename=key_file,
        timeout=30,
        allow_agent=False,
        look_for_keys=False,
    )
    return client


def run_cmd(ssh: paramiko.SSHClient, command: str, timeout: int = 60) -> tuple[int, str, str]:
    """Execute command via SSH and return (exit_code, stdout, stderr)."""
    _, stdout, stderr = ssh.exec_command(command, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    return exit_code, stdout.read().decode(), stderr.read().decode()


def main() -> int:
    parser = argparse.ArgumentParser(description="Tear down NIM container on remote host")
    parser.add_argument("--host", required=True, help="Remote host IP/hostname")
    parser.add_argument("--key-file", required=True, help="SSH private key path")
    parser.add_argument("--user", default="ubuntu", help="SSH username")
    parser.add_argument("--container-name", default="isv-nim", help="Docker container name")
    parser.add_argument("--remove-image", action="store_true", help="Also remove the container image")
    args = parser.parse_args()

    result: dict[str, Any] = {
        "success": False,
        "platform": "vm",
        "container_removed": False,
        "image_removed": False,
        "container_name": args.container_name,
    }

    ssh = None
    try:
        ssh = ssh_connect(args.host, args.user, args.key_file)

        try:
            # Get image name before removing container (for optional image removal)
            image_name = None
            if args.remove_image:
                exit_code, stdout, _ = run_cmd(
                    ssh, f"docker inspect -f '{{{{.Config.Image}}}}' {args.container_name} 2>/dev/null"
                )
                if exit_code == 0:
                    image_name = stdout.strip()

            # Stop and remove container
            print(f"Stopping container: {args.container_name}", file=sys.stderr)
            exit_code, _, stderr_out = run_cmd(ssh, f"docker rm -f {args.container_name} 2>&1")
            result["container_removed"] = exit_code == 0 or "No such container" in stderr_out

            # Optionally remove image
            if args.remove_image and image_name:
                print(f"Removing image: {image_name}", file=sys.stderr)
                exit_code, _, _ = run_cmd(ssh, f"docker rmi {image_name} 2>&1", timeout=120)
                result["image_removed"] = exit_code == 0

            result["success"] = result["container_removed"]
        finally:
            if ssh is not None and hasattr(ssh, "close"):
                ssh.close()

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
