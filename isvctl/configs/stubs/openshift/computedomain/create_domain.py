#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Create a ComputeDomain spanning multiple GPU nodes.

Creates a ComputeDomain CR and waits for IMEX channels to be
established between the specified nodes.

Environment:
    CD_NAMESPACE: Namespace (default: ncp-computedomain-validation)
    CD_TRAY_SIZE: GPUs per tray (default: 4)
"""

import json
import os
import subprocess
import sys
import time
from typing import Any

NAMESPACE = os.environ.get("CD_NAMESPACE", "ncp-computedomain-validation")
DOMAIN_NAME = "ncp-test-domain"


def run_kubectl(*args: str, input_data: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["kubectl"] + list(args), capture_output=True, text=True,
                          input=input_data, timeout=120)


def main() -> int:
    tray_size = int(os.environ.get("CD_TRAY_SIZE", "4"))

    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "domain_name": DOMAIN_NAME,
        "imex_channels_ready": False,
    }

    try:
        run_kubectl("create", "namespace", NAMESPACE)

        # Get GPU nodes
        r = run_kubectl("get", "nodes", "-l", "nvidia.com/gpu.present=true",
                        "-o", "jsonpath={.items[*].metadata.name}")
        gpu_nodes = r.stdout.strip().split() if r.returncode == 0 and r.stdout.strip() else []

        if len(gpu_nodes) < 2:
            result["error"] = f"Need at least 2 GPU nodes, found {len(gpu_nodes)}"
            print(json.dumps(result, indent=2))
            return 1

        result["gpu_nodes"] = gpu_nodes
        result["gpu_count"] = len(gpu_nodes) * tray_size
        result["tray_size"] = tray_size

        # Create ComputeDomain
        cd_yaml = f"""
apiVersion: nvidia.com/v1alpha1
kind: ComputeDomain
metadata:
  name: {DOMAIN_NAME}
  namespace: {NAMESPACE}
spec:
  gpuCount: {len(gpu_nodes) * tray_size}
"""
        run_kubectl("delete", "computedomain", DOMAIN_NAME, "-n", NAMESPACE, "--ignore-not-found")
        r = run_kubectl("apply", "-f", "-", input_data=cd_yaml)
        if r.returncode != 0:
            result["error"] = f"Failed to create ComputeDomain: {r.stderr}"
            print(json.dumps(result, indent=2))
            return 1

        # Wait for IMEX channels
        print("Waiting for IMEX channels...", file=sys.stderr)
        deadline = time.time() + 300
        while time.time() < deadline:
            r = run_kubectl("get", "computedomain", DOMAIN_NAME, "-n", NAMESPACE,
                            "-o", "jsonpath={.status.phase}")
            phase = r.stdout.strip() if r.returncode == 0 else ""
            if phase == "Ready":
                result["imex_channels_ready"] = True
                break
            print(f"  ComputeDomain phase: {phase}", file=sys.stderr)
            time.sleep(15)

        result["domain_created"] = True
        result["success"] = result["imex_channels_ready"]

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
