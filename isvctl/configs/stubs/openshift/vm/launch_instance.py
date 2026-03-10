#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Create a GPU-enabled VirtualMachine via KubeVirt.

Creates a VirtualMachine CR with GPU passthrough (VFIO), waits for
it to reach Running state, and outputs connection info for SSH checks.

Environment:
    VM_NAMESPACE:   Namespace (default: ncp-vm-validation)
    VM_GPU_COUNT:   GPUs to passthrough (default: 1)
    VM_GPU_DEVICE:  GPU device name (default: auto-detect from node labels)
    VM_MEMORY:      VM memory (default: 16Gi)
    VM_CPUS:        VM CPU cores (default: 8)
    VM_DISK_SIZE:   Root disk size (default: 50Gi)
    VM_IMAGE_URL:   Cloud image URL (RHEL/CentOS/Fedora qcow2)
    VM_SSH_PUBKEY:  SSH public key for cloud-user access
    VM_SSH_KEY:     SSH private key path (for framework SSH checks)
"""

import json
import os
import subprocess
import sys
import time
from typing import Any

NAMESPACE = os.environ.get("VM_NAMESPACE", "ncp-vm-validation")
VM_NAME = "ncp-gpu-vm"


def run_kubectl(*args: str, input_data: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["kubectl"] + list(args), capture_output=True, text=True,
                          input=input_data, timeout=120)


def detect_gpu_device() -> str:
    """Auto-detect GPU device name from node labels."""
    r = run_kubectl("get", "nodes", "-l", "nvidia.com/gpu.present=true",
                    "-o", "jsonpath={.items[0].metadata.labels.nvidia\\.com/gpu\\.product}")
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip().replace(" ", "_")
    return "nvidia.com/GH200"


def main() -> int:
    gpu_count = int(os.environ.get("VM_GPU_COUNT", "1"))
    gpu_device = os.environ.get("VM_GPU_DEVICE", "") or detect_gpu_device()
    memory = os.environ.get("VM_MEMORY", "16Gi")
    cpus = int(os.environ.get("VM_CPUS", "8"))
    disk_size = os.environ.get("VM_DISK_SIZE", "50Gi")
    image_url = os.environ.get("VM_IMAGE_URL", "")
    ssh_pubkey = os.environ.get("VM_SSH_PUBKEY", "")
    ssh_key = os.environ.get("VM_SSH_KEY", "")

    result: dict[str, Any] = {
        "success": False,
        "platform": "vm",
        "instance_id": VM_NAME,
    }

    if not image_url:
        result["error"] = "VM_IMAGE_URL is required (path to qcow2 cloud image)"
        print(json.dumps(result, indent=2))
        return 1

    try:
        # Create namespace
        run_kubectl("create", "namespace", NAMESPACE)

        # Build GPU devices list
        gpus_yaml = ""
        for i in range(gpu_count):
            gpus_yaml += f"""
        - deviceName: {gpu_device}
          name: gpu-{i}"""

        # Cloud-init user data
        cloud_init = """
#cloud-config
user: cloud-user
ssh_authorized_keys: []
"""
        if ssh_pubkey:
            cloud_init = f"""
#cloud-config
user: cloud-user
ssh_authorized_keys:
  - {ssh_pubkey}
"""

        # VirtualMachine CR
        vm_yaml = f"""
apiVersion: kubevirt.io/v1
kind: VirtualMachine
metadata:
  name: {VM_NAME}
  namespace: {NAMESPACE}
spec:
  running: true
  template:
    spec:
      domain:
        cpu:
          cores: {cpus}
        memory:
          guest: {memory}
        devices:
          disks:
            - name: rootdisk
              disk:
                bus: virtio
            - name: cloudinitdisk
              disk:
                bus: virtio
          gpus:{gpus_yaml}
          interfaces:
            - name: default
              masquerade: {{}}
        resources:
          requests:
            memory: {memory}
      networks:
        - name: default
          pod: {{}}
      volumes:
        - name: rootdisk
          dataVolume:
            name: {VM_NAME}-rootdisk
        - name: cloudinitdisk
          cloudInitNoCloud:
            userData: |
              {cloud_init.strip()}
  dataVolumeTemplates:
    - metadata:
        name: {VM_NAME}-rootdisk
      spec:
        source:
          http:
            url: "{image_url}"
        storage:
          accessModes:
            - ReadWriteOnce
          resources:
            requests:
              storage: {disk_size}
"""
        # Delete existing VM if any
        run_kubectl("delete", "vm", VM_NAME, "-n", NAMESPACE, "--ignore-not-found")
        time.sleep(5)

        r = run_kubectl("apply", "-f", "-", input_data=vm_yaml)
        if r.returncode != 0:
            result["error"] = f"Failed to create VM: {r.stderr}"
            print(json.dumps(result, indent=2))
            return 1

        # Wait for VMI to be Running
        print(f"Waiting for VM {VM_NAME} to start...", file=sys.stderr)
        deadline = time.time() + 600
        while time.time() < deadline:
            r = run_kubectl("get", "vmi", VM_NAME, "-n", NAMESPACE,
                            "-o", "jsonpath={.status.phase}")
            if r.returncode == 0 and r.stdout.strip() == "Running":
                break
            time.sleep(10)
        else:
            result["error"] = "VM did not reach Running state"
            print(json.dumps(result, indent=2))
            return 1

        # Get VM IP
        r = run_kubectl("get", "vmi", VM_NAME, "-n", NAMESPACE,
                        "-o", "jsonpath={.status.interfaces[0].ipAddress}")
        vm_ip = r.stdout.strip() if r.returncode == 0 else ""

        if not vm_ip:
            # Fallback: try pod IP
            r = run_kubectl("get", "vmi", VM_NAME, "-n", NAMESPACE,
                            "-o", "jsonpath={.status.nodeName}")
            vm_ip = "pending"

        # Wait for SSH
        if vm_ip and vm_ip != "pending":
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
                    print("SSH ready.", file=sys.stderr)
                    break
                time.sleep(10)

        result["public_ip"] = vm_ip
        result["private_ip"] = vm_ip
        result["state"] = "running"
        result["ssh_user"] = "cloud-user"
        result["key_file"] = ssh_key
        result["vpc_id"] = NAMESPACE
        result["success"] = True

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
