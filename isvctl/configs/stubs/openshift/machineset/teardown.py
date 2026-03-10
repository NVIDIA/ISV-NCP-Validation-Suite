#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Delete MachineSet, MachineAutoscaler, and test namespace.

Environment:
    MACHINESET_NAME:  MachineSet name (default: ncp-gpu-workers)
    TEARDOWN_ENABLED: Must be "true" to delete MachineSet (default: false)

Output: {"success": true, "resources_deleted": [...]}
"""

import json
import os
import subprocess
import sys
import time
from typing import Any

MS_NAMESPACE = "openshift-machine-api"
TEST_NAMESPACE = os.environ.get("K8S_NAMESPACE", "ncp-machineset-validation")


def run_oc(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["oc"] + list(args), capture_output=True, text=True, timeout=120)


def run_kubectl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["kubectl"] + list(args), capture_output=True, text=True, timeout=120)


def main() -> int:
    ms_name = os.environ.get("MACHINESET_NAME", "ncp-gpu-workers")
    teardown_enabled = os.environ.get("TEARDOWN_ENABLED", "false").lower() == "true"

    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "resources_deleted": [],
    }

    # Always clean up test namespace
    run_kubectl("delete", "namespace", TEST_NAMESPACE, "--ignore-not-found")
    result["resources_deleted"].append(f"namespace/{TEST_NAMESPACE}")

    if not teardown_enabled:
        result["success"] = True
        result["message"] = "MachineSet preserved (TEARDOWN_ENABLED != true)"
        print(json.dumps(result, indent=2))
        return 0

    # Delete MachineAutoscaler
    run_oc("delete", "machineautoscaler", f"{ms_name}-autoscaler",
           "-n", MS_NAMESPACE, "--ignore-not-found")
    result["resources_deleted"].append(f"machineautoscaler/{ms_name}-autoscaler")

    # Scale to 0 first (graceful)
    run_oc("scale", "machineset", ms_name, "-n", MS_NAMESPACE, "--replicas=0")
    print("Waiting for machines to deprovision...", file=sys.stderr)

    deadline = time.time() + 600
    while time.time() < deadline:
        r = run_oc("get", "machines", "-n", MS_NAMESPACE, "-l",
                   f"machine.openshift.io/cluster-api-machineset={ms_name}",
                   "--no-headers")
        if not r.stdout.strip():
            break
        time.sleep(15)

    # Delete MachineSet
    run_oc("delete", "machineset", ms_name, "-n", MS_NAMESPACE, "--ignore-not-found")
    result["resources_deleted"].append(f"machineset/{ms_name}")

    result["success"] = True

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
