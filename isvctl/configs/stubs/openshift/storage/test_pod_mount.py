#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Test pod mount with ODF-backed PVC.

Creates a pod that mounts the RBD PVC from test_pvc_binding, writes
data, reads it back, and verifies integrity.

Output: {"success": true, "write_ok": true, "read_ok": true, "data_matches": true}
"""

import json
import os
import subprocess
import sys
import time
from typing import Any


NAMESPACE = os.environ.get("K8S_NAMESPACE", "ncp-storage-validation")


def run_kubectl(*args: str, input_data: str | None = None) -> subprocess.CompletedProcess[str]:
    cmd = ["kubectl"] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, input=input_data, timeout=120)


def main() -> int:
    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "write_ok": False,
        "read_ok": False,
        "data_matches": False,
    }

    pod_name = "ncp-storage-test-pod"

    try:
        # Check if the RBD PVC exists (created by test_pvc_binding)
        r = run_kubectl("get", "pvc", "ncp-test-rbd", "-n", NAMESPACE, "--no-headers")
        if r.returncode != 0:
            result["error"] = "RBD PVC ncp-test-rbd not found. Run test_pvc_binding first."
            print(json.dumps(result, indent=2))
            return 1

        # Create test pod mounting the PVC
        pod_yaml = f"""
apiVersion: v1
kind: Pod
metadata:
  name: {pod_name}
  namespace: {NAMESPACE}
spec:
  containers:
    - name: test
      image: registry.access.redhat.com/ubi9/ubi-minimal:latest
      command: ["sleep", "300"]
      volumeMounts:
        - name: storage
          mountPath: /data
  volumes:
    - name: storage
      persistentVolumeClaim:
        claimName: ncp-test-rbd
  restartPolicy: Never
"""
        run_kubectl("delete", "pod", pod_name, "-n", NAMESPACE, "--ignore-not-found")
        run_kubectl("apply", "-f", "-", input_data=pod_yaml)

        # Wait for pod to be Running
        print("Waiting for test pod...", file=sys.stderr)
        deadline = time.time() + 120
        while time.time() < deadline:
            r = run_kubectl("get", "pod", pod_name, "-n", NAMESPACE,
                            "-o", "jsonpath={.status.phase}")
            if r.returncode == 0 and r.stdout.strip() == "Running":
                break
            time.sleep(5)
        else:
            result["error"] = "Test pod did not reach Running state"
            print(json.dumps(result, indent=2))
            return 1

        # Write test data
        test_data = "ncp-storage-validation-ok"
        r = run_kubectl("exec", pod_name, "-n", NAMESPACE, "--",
                        "sh", "-c", f"echo '{test_data}' > /data/test.txt")
        result["write_ok"] = r.returncode == 0

        # Read test data back
        r = run_kubectl("exec", pod_name, "-n", NAMESPACE, "--",
                        "cat", "/data/test.txt")
        result["read_ok"] = r.returncode == 0
        result["data_matches"] = r.stdout.strip() == test_data

        result["success"] = result["write_ok"] and result["read_ok"] and result["data_matches"]

    except Exception as e:
        result["error"] = str(e)
    finally:
        # Clean up pod
        run_kubectl("delete", "pod", pod_name, "-n", NAMESPACE, "--ignore-not-found")

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
