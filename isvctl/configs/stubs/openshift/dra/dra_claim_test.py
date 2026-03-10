#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Test ResourceClaim allocation with DRA driver.

Creates a ResourceClaim for a GPU and a pod that references it,
verifies the claim is allocated and the pod can access the GPU.
"""

import json
import os
import subprocess
import sys
import time
from typing import Any

NAMESPACE = os.environ.get("K8S_NAMESPACE", "ncp-dra-validation")


def run_kubectl(*args: str, input_data: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["kubectl"] + list(args), capture_output=True, text=True,
                          input=input_data, timeout=120)


def main() -> int:
    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "claim_allocated": False,
        "gpu_accessible": False,
    }

    try:
        run_kubectl("create", "namespace", NAMESPACE)

        # Detect ResourceClass name
        r = run_kubectl("get", "resourceclass", "--no-headers")
        rc_name = ""
        if r.returncode == 0:
            for line in r.stdout.strip().split("\n"):
                if "gpu" in line.lower() or "nvidia" in line.lower():
                    rc_name = line.split()[0]
                    break

        if not rc_name:
            result["error"] = "No GPU ResourceClass found"
            print(json.dumps(result, indent=2))
            return 1

        # Create ResourceClaim + Pod
        manifest = f"""
apiVersion: resource.k8s.io/v1alpha3
kind: ResourceClaim
metadata:
  name: ncp-gpu-claim
  namespace: {NAMESPACE}
spec:
  devices:
    requests:
      - name: gpu
        deviceClassName: {rc_name}
        count: 1
---
apiVersion: v1
kind: Pod
metadata:
  name: ncp-dra-test
  namespace: {NAMESPACE}
spec:
  restartPolicy: Never
  containers:
    - name: gpu-test
      image: nvcr.io/nvidia/cuda:12.8.0-base-ubi9
      command: ["nvidia-smi"]
      resources:
        claims:
          - name: gpu
  resourceClaims:
    - name: gpu
      resourceClaimName: ncp-gpu-claim
"""
        run_kubectl("delete", "pod", "ncp-dra-test", "-n", NAMESPACE, "--ignore-not-found")
        run_kubectl("delete", "resourceclaim", "ncp-gpu-claim", "-n", NAMESPACE, "--ignore-not-found")
        time.sleep(2)

        r = run_kubectl("apply", "-f", "-", input_data=manifest)
        if r.returncode != 0:
            result["error"] = f"Failed to create DRA resources: {r.stderr}"
            print(json.dumps(result, indent=2))
            return 1

        # Wait for claim allocation
        print("Waiting for ResourceClaim allocation...", file=sys.stderr)
        deadline = time.time() + 120
        while time.time() < deadline:
            r = run_kubectl("get", "resourceclaim", "ncp-gpu-claim", "-n", NAMESPACE,
                            "-o", "jsonpath={.status.allocation}")
            if r.returncode == 0 and r.stdout.strip():
                result["claim_allocated"] = True
                break
            time.sleep(5)

        # Wait for pod completion
        print("Waiting for GPU test pod...", file=sys.stderr)
        deadline = time.time() + 180
        while time.time() < deadline:
            r = run_kubectl("get", "pod", "ncp-dra-test", "-n", NAMESPACE,
                            "-o", "jsonpath={.status.phase}")
            phase = r.stdout.strip() if r.returncode == 0 else ""
            if phase == "Succeeded":
                result["gpu_accessible"] = True
                break
            if phase == "Failed":
                r = run_kubectl("logs", "ncp-dra-test", "-n", NAMESPACE)
                result["error"] = f"Pod failed: {r.stdout[:200]}"
                break
            time.sleep(10)

        if result["gpu_accessible"]:
            r = run_kubectl("logs", "ncp-dra-test", "-n", NAMESPACE)
            result["nvidia_smi_output"] = r.stdout[:500] if r.returncode == 0 else ""

        result["success"] = result["claim_allocated"] and result["gpu_accessible"]

    except Exception as e:
        result["error"] = str(e)
    finally:
        run_kubectl("delete", "pod", "ncp-dra-test", "-n", NAMESPACE, "--ignore-not-found")
        run_kubectl("delete", "resourceclaim", "ncp-gpu-claim", "-n", NAMESPACE, "--ignore-not-found")

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
