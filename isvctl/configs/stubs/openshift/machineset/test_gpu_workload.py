#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Run a single-node GPU workload on the MachineSet nodes.

Schedules a GPU pod on one of the MachineSet-provisioned nodes to
verify GPU scheduling works on dynamically provisioned machines.

Output: {"success": true, "gpu_detected": true, "node": "<name>"}
"""

import json
import os
import subprocess
import sys
import time
from typing import Any

NAMESPACE = os.environ.get("K8S_NAMESPACE", "ncp-machineset-validation")


def run_kubectl(*args: str, input_data: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["kubectl"] + list(args), capture_output=True, text=True,
                          input=input_data, timeout=120)


def main() -> int:
    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "gpu_detected": False,
    }

    try:
        run_kubectl("create", "namespace", NAMESPACE)

        pod_yaml = f"""
apiVersion: v1
kind: Pod
metadata:
  name: ncp-gpu-test
  namespace: {NAMESPACE}
spec:
  restartPolicy: Never
  containers:
    - name: gpu-test
      image: nvcr.io/nvidia/cuda:12.8.0-base-ubi9
      command: ["nvidia-smi"]
      resources:
        limits:
          nvidia.com/gpu: "1"
"""
        run_kubectl("delete", "pod", "ncp-gpu-test", "-n", NAMESPACE, "--ignore-not-found")
        run_kubectl("apply", "-f", "-", input_data=pod_yaml)

        # Wait for completion
        print("Waiting for GPU test pod...", file=sys.stderr)
        deadline = time.time() + 300
        while time.time() < deadline:
            r = run_kubectl("get", "pod", "ncp-gpu-test", "-n", NAMESPACE,
                            "-o", "jsonpath={.status.phase}")
            phase = r.stdout.strip() if r.returncode == 0 else ""
            if phase == "Succeeded":
                result["gpu_detected"] = True
                break
            if phase == "Failed":
                result["error"] = "GPU test pod failed"
                break
            time.sleep(10)

        # Get which node it ran on
        r = run_kubectl("get", "pod", "ncp-gpu-test", "-n", NAMESPACE,
                        "-o", "jsonpath={.spec.nodeName}")
        result["node"] = r.stdout.strip() if r.returncode == 0 else ""

        # Get nvidia-smi output
        r = run_kubectl("logs", "ncp-gpu-test", "-n", NAMESPACE)
        if r.returncode == 0:
            result["nvidia_smi_output"] = r.stdout[:500]

        run_kubectl("delete", "pod", "ncp-gpu-test", "-n", NAMESPACE, "--ignore-not-found")

        result["success"] = result["gpu_detected"]

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
