#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Test PVC binding with ODF StorageClasses.

Creates PVCs for both CephRBD and CephFS StorageClasses and verifies
they reach Bound state.

Output: {"success": true, "rbd_pvc_bound": true, "cephfs_pvc_bound": true}
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


def create_and_wait_pvc(name: str, storage_class: str, timeout: int = 120) -> bool:
    """Create a PVC and wait for it to bind."""
    pvc_yaml = f"""
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: {name}
  namespace: {NAMESPACE}
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
  storageClassName: {storage_class}
"""
    run_kubectl("apply", "-f", "-", input_data=pvc_yaml)

    deadline = time.time() + timeout
    while time.time() < deadline:
        r = run_kubectl("get", "pvc", name, "-n", NAMESPACE,
                        "-o", "jsonpath={.status.phase}")
        if r.returncode == 0 and r.stdout.strip() == "Bound":
            return True
        time.sleep(5)
    return False


def main() -> int:
    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "rbd_pvc_bound": False,
        "cephfs_pvc_bound": False,
    }

    try:
        # Ensure namespace exists
        run_kubectl("create", "namespace", NAMESPACE)

        # Detect available StorageClass names
        r = run_kubectl("get", "storageclass", "-o", "jsonpath={.items[*].metadata.name}")
        classes = r.stdout.strip().split() if r.returncode == 0 else []

        # Find the RBD StorageClass
        rbd_class = ""
        for name in ["ocs-storagecluster-ceph-rbd", "ocs-external-storagecluster-ceph-rbd"]:
            if name in classes:
                rbd_class = name
                break

        # Find the CephFS StorageClass
        cephfs_class = ""
        for name in ["ocs-storagecluster-cephfs", "ocs-external-storagecluster-cephfs"]:
            if name in classes:
                cephfs_class = name
                break

        # Test RBD PVC
        if rbd_class:
            print(f"Creating RBD PVC with {rbd_class}...", file=sys.stderr)
            result["rbd_pvc_bound"] = create_and_wait_pvc("ncp-test-rbd", rbd_class)
            print(f"  RBD PVC bound: {result['rbd_pvc_bound']}", file=sys.stderr)
        else:
            print("No CephRBD StorageClass found, skipping.", file=sys.stderr)

        # Test CephFS PVC
        if cephfs_class:
            print(f"Creating CephFS PVC with {cephfs_class}...", file=sys.stderr)
            result["cephfs_pvc_bound"] = create_and_wait_pvc("ncp-test-cephfs", cephfs_class)
            print(f"  CephFS PVC bound: {result['cephfs_pvc_bound']}", file=sys.stderr)
        else:
            print("No CephFS StorageClass found, skipping.", file=sys.stderr)

        result["success"] = result["rbd_pvc_bound"] and result["cephfs_pvc_bound"]

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
