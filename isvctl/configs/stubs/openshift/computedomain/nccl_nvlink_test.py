#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""NCCL AllReduce over NVLink within the ComputeDomain.

Runs an NCCL all_reduce_perf job using IMEX channels across
multiple nodes in the ComputeDomain.
"""

import json
import os
import re
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
    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "status": "failed",
        "bus_bandwidth_gbps": 0.0,
    }

    try:
        job_yaml = f"""
apiVersion: batch/v1
kind: Job
metadata:
  name: ncp-nccl-nvlink
  namespace: {NAMESPACE}
  labels:
    nvidia.com/compute-domain: {DOMAIN_NAME}
spec:
  backoffLimit: 0
  template:
    metadata:
      labels:
        nvidia.com/compute-domain: {DOMAIN_NAME}
    spec:
      restartPolicy: Never
      containers:
        - name: nccl
          image: nvcr.io/nvidia/pytorch:24.10-py3
          command:
            - bash
            - -c
            - |
              /usr/local/bin/all_reduce_perf -b 1M -e 1G -f 2 -g $(nvidia-smi -L | wc -l)
          resources:
            limits:
              nvidia.com/gpu: "4"
"""
        run_kubectl("delete", "job", "ncp-nccl-nvlink", "-n", NAMESPACE, "--ignore-not-found")
        time.sleep(2)
        r = run_kubectl("apply", "-f", "-", input_data=job_yaml)
        if r.returncode != 0:
            result["error"] = f"Failed to create NCCL job: {r.stderr}"
            print(json.dumps(result, indent=2))
            return 1

        # Wait for completion
        print("Waiting for NCCL NVLink job...", file=sys.stderr)
        deadline = time.time() + 600
        while time.time() < deadline:
            r = run_kubectl("get", "job", "ncp-nccl-nvlink", "-n", NAMESPACE,
                            "-o", "jsonpath={.status.succeeded}")
            if r.returncode == 0 and r.stdout.strip() == "1":
                break
            r2 = run_kubectl("get", "job", "ncp-nccl-nvlink", "-n", NAMESPACE,
                             "-o", "jsonpath={.status.failed}")
            if r2.returncode == 0 and r2.stdout.strip() == "1":
                result["error"] = "NCCL job failed"
                break
            time.sleep(15)

        # Get logs and parse bandwidth
        r = run_kubectl("logs", "-l", "job-name=ncp-nccl-nvlink", "-n", NAMESPACE)
        if r.returncode == 0:
            result["logs"] = r.stdout[-2000:]
            # Parse peak bus bandwidth from all_reduce_perf output
            bw_values = re.findall(r'(\d+\.\d+)\s*$', r.stdout, re.MULTILINE)
            if bw_values:
                peak_bw = max(float(v) for v in bw_values)
                result["bus_bandwidth_gbps"] = peak_bw

        result["status"] = "passed" if result["bus_bandwidth_gbps"] > 0 else "failed"
        result["success"] = result["status"] == "passed"

    except Exception as e:
        result["error"] = str(e)
    finally:
        run_kubectl("delete", "job", "ncp-nccl-nvlink", "-n", NAMESPACE, "--ignore-not-found")

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
