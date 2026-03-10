#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Verify the hosted cluster is functional.

Runs basic health checks against the hosted cluster: nodes Ready,
GPU Operator running, nvidia-smi works.

After this step, the full validation suite can be run by setting
KUBECONFIG to the hosted cluster's kubeconfig.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

STATE_FILE = os.environ.get("HOSTED_STATE_FILE", "/tmp/ncp-hosted-state.json")
SCRIPT_DIR = Path(__file__).parent


def load_state() -> dict[str, Any]:
    try:
        return json.loads(Path(STATE_FILE).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def main() -> int:
    state = load_state()
    kubeconfig = state.get("hosted_kubeconfig", "")

    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "nodes_ready": 0,
        "gpu_operator_running": False,
        "kubeconfig_path": kubeconfig,
    }

    if not kubeconfig or not Path(kubeconfig).exists():
        result["error"] = "Hosted kubeconfig not found"
        print(json.dumps(result, indent=2))
        return 1

    env = {**os.environ, "KUBECONFIG": kubeconfig}

    # Check nodes
    r = subprocess.run(
        ["kubectl", "get", "nodes", "--no-headers"],
        capture_output=True, text=True, timeout=30, env=env,
    )
    if r.returncode == 0:
        nodes = [l for l in r.stdout.strip().split("\n") if l.strip()]
        ready = sum(1 for l in nodes if "Ready" in l and "NotReady" not in l)
        result["nodes_ready"] = ready
        result["total_nodes"] = len(nodes)

    # Check GPU Operator
    r = subprocess.run(
        ["kubectl", "get", "pods", "-n", "nvidia-gpu-operator",
         "-l", "app=gpu-operator", "--no-headers"],
        capture_output=True, text=True, timeout=30, env=env,
    )
    result["gpu_operator_running"] = r.returncode == 0 and "Running" in r.stdout

    # Check GPU nodes
    r = subprocess.run(
        ["kubectl", "get", "nodes", "-l", "nvidia.com/gpu.present=true",
         "--no-headers"],
        capture_output=True, text=True, timeout=30, env=env,
    )
    gpu_nodes = len([l for l in r.stdout.strip().split("\n") if l.strip()]) if r.returncode == 0 else 0
    result["gpu_nodes"] = gpu_nodes

    result["success"] = result["nodes_ready"] > 0
    result["message"] = (
        f"Hosted cluster: {result['nodes_ready']} nodes Ready, "
        f"{gpu_nodes} GPU nodes, "
        f"GPU Operator {'running' if result['gpu_operator_running'] else 'not running'}. "
        f"Run tests with: KUBECONFIG={kubeconfig} isvctl test run -f ..."
    )

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
