#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Clean up storage test resources.

Deletes test PVCs, pods, and the test namespace. Does NOT remove
ODF or the StorageCluster — those stay deployed for other tests.

Output: {"success": true, "resources_deleted": [...]}
"""

import json
import os
import subprocess
import sys
from typing import Any


NAMESPACE = os.environ.get("K8S_NAMESPACE", "ncp-storage-validation")


def run_kubectl(*args: str) -> subprocess.CompletedProcess[str]:
    cmd = ["kubectl"] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)


def main() -> int:
    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "resources_deleted": [],
    }

    # Delete test PVCs
    for pvc in ["ncp-test-rbd", "ncp-test-cephfs"]:
        r = run_kubectl("delete", "pvc", pvc, "-n", NAMESPACE, "--ignore-not-found")
        if r.returncode == 0:
            result["resources_deleted"].append(f"pvc/{pvc}")

    # Delete test namespace
    r = run_kubectl("delete", "namespace", NAMESPACE, "--ignore-not-found")
    if r.returncode == 0:
        result["resources_deleted"].append(f"namespace/{NAMESPACE}")

    result["success"] = True
    result["message"] = "Test resources cleaned up; ODF stays deployed"

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
