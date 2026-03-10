#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Delete the GPU VM and test namespace."""

import json
import os
import subprocess
import sys
import time
from typing import Any

NAMESPACE = os.environ.get("VM_NAMESPACE", "ncp-vm-validation")
VM_NAME = "ncp-gpu-vm"


def run_kubectl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["kubectl"] + list(args), capture_output=True, text=True, timeout=120)


def main() -> int:
    result: dict[str, Any] = {
        "success": False,
        "platform": "vm",
        "resources_deleted": [],
    }

    # Delete VM
    r = run_kubectl("delete", "vm", VM_NAME, "-n", NAMESPACE, "--ignore-not-found")
    if r.returncode == 0:
        result["resources_deleted"].append(f"vm/{VM_NAME}")

    # Wait for VMI to terminate
    deadline = time.time() + 120
    while time.time() < deadline:
        r = run_kubectl("get", "vmi", VM_NAME, "-n", NAMESPACE, "--no-headers")
        if r.returncode != 0 or not r.stdout.strip():
            break
        time.sleep(10)

    # Delete DataVolume
    run_kubectl("delete", "dv", f"{VM_NAME}-rootdisk", "-n", NAMESPACE, "--ignore-not-found")
    result["resources_deleted"].append(f"dv/{VM_NAME}-rootdisk")

    # Delete namespace
    run_kubectl("delete", "namespace", NAMESPACE, "--ignore-not-found")
    result["resources_deleted"].append(f"namespace/{NAMESPACE}")

    result["success"] = True

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
