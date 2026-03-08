#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Test MachineSet scale-up by increasing replicas.

Scales the MachineSet up by adding replicas and waits for the new
machines to provision and join as Ready nodes.

Environment:
    MACHINESET_NAME:         MachineSet name (default: ncp-gpu-workers)
    MACHINESET_SCALE_UP_TO:  Target replicas (default: current + 1)

Output: {"success": true, "scaled_to": N, "nodes_after": N}
"""

import json
import os
import subprocess
import sys
import time
from typing import Any

NAMESPACE = "openshift-machine-api"


def run_oc(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["oc"] + list(args), capture_output=True, text=True, timeout=120)


def run_kubectl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["kubectl"] + list(args), capture_output=True, text=True, timeout=120)


def main() -> int:
    ms_name = os.environ.get("MACHINESET_NAME", "ncp-gpu-workers")

    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
    }

    try:
        # Get current replicas
        r = run_oc("get", "machineset", ms_name, "-n", NAMESPACE,
                   "-o", "jsonpath={.spec.replicas}")
        current = int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else 0
        result["replicas_before"] = current

        target = int(os.environ.get("MACHINESET_SCALE_UP_TO", str(current + 1)))
        if target <= current:
            result["success"] = True
            result["scaled_to"] = current
            result["nodes_after"] = current
            result["message"] = "Already at or above target replicas"
            print(json.dumps(result, indent=2))
            return 0

        # Scale up
        print(f"Scaling {ms_name} from {current} to {target}...", file=sys.stderr)
        r = run_oc("scale", "machineset", ms_name, "-n", NAMESPACE,
                   f"--replicas={target}")
        if r.returncode != 0:
            result["error"] = f"Scale failed: {r.stderr}"
            print(json.dumps(result, indent=2))
            return 1

        # Wait for new machines to be ready
        print("Waiting for new machines to provision...", file=sys.stderr)
        deadline = time.time() + 1500
        while time.time() < deadline:
            r = run_oc("get", "machineset", ms_name, "-n", NAMESPACE,
                       "-o", "jsonpath={.status.readyReplicas}")
            ready = int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else 0
            if ready >= target:
                break
            print(f"  Ready: {ready}/{target}", file=sys.stderr)
            time.sleep(30)

        # Count nodes
        r = run_kubectl("get", "nodes", "-l",
                        f"machine.openshift.io/cluster-api-machineset={ms_name}",
                        "--no-headers")
        nodes = [l for l in r.stdout.strip().split("\n") if l.strip()] if r.returncode == 0 else []

        result["scaled_to"] = target
        result["nodes_after"] = len(nodes)
        result["success"] = len(nodes) >= target

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
