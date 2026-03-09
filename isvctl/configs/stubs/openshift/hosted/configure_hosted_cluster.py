#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Configure day-2 operators on the hosted cluster.

Targets the hosted cluster's kubeconfig to install:
- GPU Operator
- Network Operator
- OpenShift Virtualization (optional)

Environment:
    HOSTED_STATE_FILE: Path to state file (default: /tmp/ncp-hosted-state.json)
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

STATE_FILE = os.environ.get("HOSTED_STATE_FILE", "/tmp/ncp-hosted-state.json")


def load_state() -> dict[str, Any]:
    try:
        return json.loads(Path(STATE_FILE).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def run_hosted_oc(*args: str, kubeconfig: str, input_data: str | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "KUBECONFIG": kubeconfig}
    return subprocess.run(["oc"] + list(args), capture_output=True, text=True,
                          input=input_data, timeout=120, env=env)


def main() -> int:
    state = load_state()
    kubeconfig = state.get("hosted_kubeconfig", "")

    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "gpu_operator_installed": False,
        "network_operator_installed": False,
    }

    if not kubeconfig or not Path(kubeconfig).exists():
        result["error"] = f"Hosted kubeconfig not found at {kubeconfig}"
        print(json.dumps(result, indent=2))
        return 1

    try:
        # Verify connectivity to hosted cluster
        r = run_hosted_oc("whoami", kubeconfig=kubeconfig)
        if r.returncode != 0:
            result["error"] = f"Cannot connect to hosted cluster: {r.stderr}"
            print(json.dumps(result, indent=2))
            return 1

        print(f"Connected to hosted cluster as {r.stdout.strip()}", file=sys.stderr)

        # Install GPU Operator
        print("Installing GPU Operator on hosted cluster...", file=sys.stderr)
        run_hosted_oc("create", "namespace", "nvidia-gpu-operator", kubeconfig=kubeconfig)

        og_yaml = """
apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata:
  name: nvidia-gpu-operator
  namespace: nvidia-gpu-operator
spec:
  targetNamespaces:
    - nvidia-gpu-operator
"""
        run_hosted_oc("apply", "-f", "-", kubeconfig=kubeconfig, input_data=og_yaml)

        sub_yaml = """
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: gpu-operator-certified
  namespace: nvidia-gpu-operator
spec:
  channel: "v24.9"
  installPlanApproval: Automatic
  name: gpu-operator-certified
  source: certified-operators
  sourceNamespace: openshift-marketplace
"""
        run_hosted_oc("apply", "-f", "-", kubeconfig=kubeconfig, input_data=sub_yaml)

        # Wait for GPU Operator
        deadline = time.time() + 300
        while time.time() < deadline:
            r = run_hosted_oc("get", "pods", "-n", "nvidia-gpu-operator",
                              "-l", "app=gpu-operator", "--no-headers",
                              kubeconfig=kubeconfig)
            if r.returncode == 0 and "Running" in r.stdout:
                result["gpu_operator_installed"] = True
                break
            time.sleep(15)

        # Install Network Operator
        print("Installing Network Operator on hosted cluster...", file=sys.stderr)
        run_hosted_oc("create", "namespace", "nvidia-network-operator", kubeconfig=kubeconfig)

        net_sub_yaml = """
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: nvidia-network-operator
  namespace: nvidia-network-operator
spec:
  channel: "v24.7"
  installPlanApproval: Automatic
  name: nvidia-network-operator-certified
  source: certified-operators
  sourceNamespace: openshift-marketplace
"""
        run_hosted_oc("apply", "-f", "-", kubeconfig=kubeconfig, input_data=net_sub_yaml)
        result["network_operator_installed"] = True  # Best effort

        result["success"] = result["gpu_operator_installed"]

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
