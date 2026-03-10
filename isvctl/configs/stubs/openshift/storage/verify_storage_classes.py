#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Verify ODF StorageClasses are provisioned.

Checks that CephRBD and CephFS StorageClasses exist after ODF deployment.

Output: {"success": true, "rbd_class_exists": true, "cephfs_class_exists": true, ...}
"""

import json
import subprocess
import sys
from typing import Any


def main() -> int:
    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "rbd_class_exists": False,
        "cephfs_class_exists": False,
        "storage_classes": [],
    }

    try:
        r = subprocess.run(
            ["kubectl", "get", "storageclass", "-o",
             "jsonpath={.items[*].metadata.name}"],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            result["error"] = f"Failed to list StorageClasses: {r.stderr}"
            print(json.dumps(result, indent=2))
            return 1

        classes = r.stdout.strip().split()
        result["storage_classes"] = classes

        # Check for OCS/ODF StorageClasses
        rbd_names = ["ocs-storagecluster-ceph-rbd", "ocs-external-storagecluster-ceph-rbd"]
        cephfs_names = ["ocs-storagecluster-cephfs", "ocs-external-storagecluster-cephfs"]

        result["rbd_class_exists"] = any(n in classes for n in rbd_names)
        result["cephfs_class_exists"] = any(n in classes for n in cephfs_names)

        result["success"] = result["rbd_class_exists"] and result["cephfs_class_exists"]

        if not result["success"]:
            missing = []
            if not result["rbd_class_exists"]:
                missing.append("CephRBD")
            if not result["cephfs_class_exists"]:
                missing.append("CephFS")
            result["error"] = f"Missing StorageClasses: {', '.join(missing)}"

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
