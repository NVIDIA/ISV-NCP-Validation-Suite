#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Create a GPU MachineSet and wait for nodes to join.

Creates a MachineSet targeting Carbide GPU instance type with the
specified initial replicas, then waits for all machines to be
provisioned and their corresponding nodes to reach Ready state.

Environment:
    CARBIDE_INSTANCE_TYPE:   Instance type for GPU machines
    CARBIDE_SITE_ID:         Site UUID
    MACHINESET_MIN_REPLICAS: Initial replicas (default: 2)
    MACHINESET_MAX_REPLICAS: Max replicas for autoscaler (default: 6)
    MACHINESET_NAME:         MachineSet name (default: ncp-gpu-workers)

Output: {"success": true, "replicas_ready": 2, "nodes_joined": 2}
"""

import json
import os
import subprocess
import sys
import time
from typing import Any


NAMESPACE = "openshift-machine-api"


def run_oc(*args: str, input_data: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["oc"] + list(args), capture_output=True, text=True,
                          input=input_data, timeout=120)


def run_kubectl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["kubectl"] + list(args), capture_output=True, text=True, timeout=120)


def main() -> int:
    instance_type = os.environ.get("CARBIDE_INSTANCE_TYPE", "")
    site_id = os.environ.get("CARBIDE_SITE_ID", "")
    min_replicas = int(os.environ.get("MACHINESET_MIN_REPLICAS", "2"))
    max_replicas = int(os.environ.get("MACHINESET_MAX_REPLICAS", "6"))
    ms_name = os.environ.get("MACHINESET_NAME", "ncp-gpu-workers")

    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "machineset_name": ms_name,
        "replicas_ready": 0,
        "nodes_joined": 0,
    }

    if not instance_type:
        result["error"] = "CARBIDE_INSTANCE_TYPE is required"
        print(json.dumps(result, indent=2))
        return 1

    try:
        # Get cluster infrastructure name for MachineSet naming
        r = run_oc("get", "infrastructure", "cluster",
                   "-o", "jsonpath={.status.infrastructureName}")
        infra_name = r.stdout.strip() if r.returncode == 0 else "cluster"

        # Check if MachineSet already exists
        r = run_oc("get", "machineset", ms_name, "-n", NAMESPACE, "--no-headers")
        if r.returncode == 0 and r.stdout.strip():
            print(f"MachineSet {ms_name} already exists.", file=sys.stderr)
        else:
            # Create MachineSet
            # The providerSpec depends on the Carbide Machine API provider
            ms_yaml = f"""
apiVersion: machine.openshift.io/v1beta1
kind: MachineSet
metadata:
  name: {ms_name}
  namespace: {NAMESPACE}
  labels:
    machine.openshift.io/cluster-api-cluster: {infra_name}
spec:
  replicas: {min_replicas}
  selector:
    matchLabels:
      machine.openshift.io/cluster-api-cluster: {infra_name}
      machine.openshift.io/cluster-api-machineset: {ms_name}
  template:
    metadata:
      labels:
        machine.openshift.io/cluster-api-cluster: {infra_name}
        machine.openshift.io/cluster-api-machineset: {ms_name}
        machine.openshift.io/cluster-api-machine-role: worker
        machine.openshift.io/cluster-api-machine-type: worker
    spec:
      providerSpec:
        value:
          apiVersion: carbide.nvidia.com/v1alpha1
          kind: CarbideMachineProviderConfig
          instanceType: "{instance_type}"
          siteId: "{site_id}"
      metadata:
        labels:
          node-role.kubernetes.io/worker: ""
          nvidia.com/gpu.present: "true"
"""
            r = run_oc("apply", "-f", "-", input_data=ms_yaml)
            if r.returncode != 0:
                result["error"] = f"Failed to create MachineSet: {r.stderr}"
                print(json.dumps(result, indent=2))
                return 1

            print(f"MachineSet {ms_name} created with {min_replicas} replicas.", file=sys.stderr)

        # Create ClusterAutoscaler and MachineAutoscaler if max > min
        if max_replicas > min_replicas:
            ma_yaml = f"""
apiVersion: autoscaling.openshift.io/v1beta1
kind: MachineAutoscaler
metadata:
  name: {ms_name}-autoscaler
  namespace: {NAMESPACE}
spec:
  minReplicas: {min_replicas}
  maxReplicas: {max_replicas}
  scaleTargetRef:
    apiVersion: machine.openshift.io/v1beta1
    kind: MachineSet
    name: {ms_name}
"""
            run_oc("apply", "-f", "-", input_data=ma_yaml)
            print(f"MachineAutoscaler created (min={min_replicas}, max={max_replicas}).", file=sys.stderr)

        # Wait for machines to be provisioned
        print("Waiting for machines to provision...", file=sys.stderr)
        deadline = time.time() + 1500  # 25 minutes for BM provisioning
        while time.time() < deadline:
            r = run_oc("get", "machineset", ms_name, "-n", NAMESPACE,
                       "-o", "jsonpath={.status.readyReplicas}")
            ready = int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else 0
            if ready >= min_replicas:
                result["replicas_ready"] = ready
                break
            print(f"  Ready: {ready}/{min_replicas}", file=sys.stderr)
            time.sleep(30)

        # Count GPU nodes that joined
        r = run_kubectl("get", "nodes", "-l",
                        f"machine.openshift.io/cluster-api-machineset={ms_name}",
                        "--no-headers")
        nodes = [l for l in r.stdout.strip().split("\n") if l.strip()] if r.returncode == 0 else []
        result["nodes_joined"] = len(nodes)
        result["node_names"] = [n.split()[0] for n in nodes]

        result["success"] = result["replicas_ready"] >= min_replicas

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
