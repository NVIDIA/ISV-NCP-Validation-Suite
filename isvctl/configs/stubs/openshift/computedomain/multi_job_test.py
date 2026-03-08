#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Test multi-job scheduling within the ComputeDomain.

Submits two GPU jobs within the same ComputeDomain and verifies
both are scheduled and complete successfully.
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
    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "jobs_submitted": 0,
        "jobs_completed": 0,
    }

    try:
        for i in range(2):
            job_yaml = f"""
apiVersion: batch/v1
kind: Job
metadata:
  name: ncp-cd-job-{i}
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
        - name: gpu-job
          image: nvcr.io/nvidia/cuda:12.8.0-base-ubi9
          command: ["nvidia-smi", "-L"]
          resources:
            limits:
              nvidia.com/gpu: "1"
"""
            run_kubectl("delete", "job", f"ncp-cd-job-{i}", "-n", NAMESPACE, "--ignore-not-found")
            r = run_kubectl("apply", "-f", "-", input_data=job_yaml)
            if r.returncode == 0:
                result["jobs_submitted"] += 1

        # Wait for jobs to complete
        print("Waiting for ComputeDomain jobs...", file=sys.stderr)
        deadline = time.time() + 300
        while time.time() < deadline:
            completed = 0
            for i in range(2):
                r = run_kubectl("get", "job", f"ncp-cd-job-{i}", "-n", NAMESPACE,
                                "-o", "jsonpath={.status.succeeded}")
                if r.returncode == 0 and r.stdout.strip() == "1":
                    completed += 1
            result["jobs_completed"] = completed
            if completed == 2:
                break
            time.sleep(10)

        result["success"] = result["jobs_completed"] == 2

    except Exception as e:
        result["error"] = str(e)
    finally:
        for i in range(2):
            run_kubectl("delete", "job", f"ncp-cd-job-{i}", "-n", NAMESPACE, "--ignore-not-found")

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
