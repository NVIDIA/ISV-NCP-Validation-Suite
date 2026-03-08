#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Restart the GPU VM and verify it comes back."""

import json
import os
import subprocess
import sys
import time
from typing import Any

NAMESPACE = os.environ.get("VM_NAMESPACE", "ncp-vm-validation")
VM_NAME = "ncp-gpu-vm"


def run_kubectl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["kubectl"] + list(args), capture_output=True, text=True, timeout=120)


def main() -> int:
    ssh_key = os.environ.get("VM_SSH_KEY", "")

    result: dict[str, Any] = {
        "success": False,
        "platform": "vm",
        "instance_id": VM_NAME,
        "reboot_initiated": False,
        "ssh_ready": False,
    }

    try:
        # Restart via virtctl or VMI delete
        r = subprocess.run(["virtctl", "restart", VM_NAME, "-n", NAMESPACE],
                           capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            # Fallback: delete VMI to trigger restart
            run_kubectl("delete", "vmi", VM_NAME, "-n", NAMESPACE)

        result["reboot_initiated"] = True
        print("Restart initiated, waiting for VMI to come back...", file=sys.stderr)
        time.sleep(15)

        # Wait for Running
        deadline = time.time() + 300
        while time.time() < deadline:
            r = run_kubectl("get", "vmi", VM_NAME, "-n", NAMESPACE,
                            "-o", "jsonpath={.status.phase}")
            if r.returncode == 0 and r.stdout.strip() == "Running":
                break
            time.sleep(10)

        # Get IP
        r = run_kubectl("get", "vmi", VM_NAME, "-n", NAMESPACE,
                        "-o", "jsonpath={.status.interfaces[0].ipAddress}")
        vm_ip = r.stdout.strip() if r.returncode == 0 else ""

        # Wait for SSH
        if vm_ip:
            print(f"Waiting for SSH on {vm_ip}...", file=sys.stderr)
            deadline = time.time() + 180
            while time.time() < deadline:
                r = subprocess.run(
                    ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5",
                     "-o", "BatchMode=yes"] +
                    (["-i", ssh_key] if ssh_key else []) +
                    [f"cloud-user@{vm_ip}", "true"],
                    capture_output=True, text=True, timeout=10,
                )
                if r.returncode == 0:
                    result["ssh_ready"] = True
                    break
                time.sleep(10)

            # Get uptime
            if result["ssh_ready"]:
                r = subprocess.run(
                    ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes"] +
                    (["-i", ssh_key] if ssh_key else []) +
                    [f"cloud-user@{vm_ip}", "cat", "/proc/uptime"],
                    capture_output=True, text=True, timeout=10,
                )
                if r.returncode == 0:
                    uptime = float(r.stdout.strip().split()[0])
                    result["uptime_seconds"] = int(uptime)

        result["public_ip"] = vm_ip
        result["private_ip"] = vm_ip
        result["state"] = "running"
        result["ssh_user"] = "cloud-user"
        result["key_file"] = ssh_key
        result["ssh_connectivity"] = result["ssh_ready"]
        result["success"] = result["reboot_initiated"] and result["ssh_ready"]

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
