#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Deploy the hosted OpenShift cluster via CAPI.

Creates a CAPI Cluster CR referencing the Carbide infrastructure
provider and the BareMetalHosts provisioned in the previous step.
Waits for the hosted cluster to be fully operational.

Environment:
    HOSTED_CLUSTER_NAME: Cluster name (default: ncp-hosted)
    HOSTED_BASE_DOMAIN:  Base DNS domain (default: from mgmt cluster)
    OCP_PULL_SECRET:     OpenShift pull secret (JSON or file path)
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

STATE_FILE = os.environ.get("HOSTED_STATE_FILE", "/tmp/ncp-hosted-state.json")


def run_kubectl(*args: str, input_data: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["kubectl"] + list(args), capture_output=True, text=True,
                          input=input_data, timeout=120)


def run_oc(*args: str, input_data: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["oc"] + list(args), capture_output=True, text=True,
                          input=input_data, timeout=120)


def load_state() -> dict[str, Any]:
    try:
        return json.loads(Path(STATE_FILE).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state: dict[str, Any]) -> None:
    Path(STATE_FILE).write_text(json.dumps(state, indent=2))


def main() -> int:
    cluster_name = os.environ.get("HOSTED_CLUSTER_NAME", "ncp-hosted")
    pull_secret = os.environ.get("OCP_PULL_SECRET", "")

    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "cluster_ready": False,
        "kubeconfig_path": "",
    }

    try:
        state = load_state()

        # Get base domain from management cluster
        base_domain = os.environ.get("HOSTED_BASE_DOMAIN", "")
        if not base_domain:
            r = run_oc("get", "ingress.config.openshift.io", "cluster",
                       "-o", "jsonpath={.spec.domain}")
            if r.returncode == 0 and r.stdout.strip():
                # apps.cluster.example.com → cluster.example.com
                base_domain = r.stdout.strip().replace("apps.", "", 1)

        cluster_ns = f"{cluster_name}"
        run_kubectl("create", "namespace", cluster_ns)

        # Create pull secret in cluster namespace
        if pull_secret:
            ps_content = pull_secret
            if os.path.isfile(pull_secret):
                ps_content = Path(pull_secret).read_text()

            ps_yaml = f"""
apiVersion: v1
kind: Secret
metadata:
  name: pull-secret
  namespace: {cluster_ns}
type: kubernetes.io/dockerconfigjson
stringData:
  .dockerconfigjson: '{ps_content}'
"""
            run_kubectl("apply", "-f", "-", input_data=ps_yaml)

        # Create CAPI Cluster CR
        worker_count = len(state.get("bmh_instance_ids", []))
        cluster_yaml = f"""
apiVersion: cluster.x-k8s.io/v1beta1
kind: Cluster
metadata:
  name: {cluster_name}
  namespace: {cluster_ns}
spec:
  clusterNetwork:
    pods:
      cidrBlocks: ["10.132.0.0/14"]
    services:
      cidrBlocks: ["172.31.0.0/16"]
  controlPlaneRef:
    apiVersion: controlplane.cluster.x-k8s.io/v1beta1
    kind: HostedControlPlane
    name: {cluster_name}
    namespace: {cluster_ns}
  infrastructureRef:
    apiVersion: infrastructure.cluster.x-k8s.io/v1alpha1
    kind: CarbideCluster
    name: {cluster_name}
    namespace: {cluster_ns}
---
apiVersion: infrastructure.cluster.x-k8s.io/v1alpha1
kind: CarbideCluster
metadata:
  name: {cluster_name}
  namespace: {cluster_ns}
spec:
  controlPlaneEndpoint:
    host: api.{cluster_name}.{base_domain}
    port: 6443
"""
        r = run_kubectl("apply", "-f", "-", input_data=cluster_yaml)
        if r.returncode != 0:
            result["error"] = f"Failed to create Cluster CR: {r.stderr}"
            print(json.dumps(result, indent=2))
            return 1

        # Wait for cluster to be provisioned
        print("Waiting for hosted cluster to be ready...", file=sys.stderr)
        kubeconfig_path = f"/tmp/{cluster_name}-kubeconfig"

        deadline = time.time() + 5400  # 90 minutes
        while time.time() < deadline:
            r = run_kubectl("get", "cluster", cluster_name, "-n", cluster_ns,
                            "-o", "jsonpath={.status.phase}")
            phase = r.stdout.strip() if r.returncode == 0 else ""

            if phase == "Provisioned":
                result["cluster_ready"] = True
                break

            print(f"  Cluster phase: {phase}", file=sys.stderr)
            time.sleep(30)

        # Extract kubeconfig
        r = run_kubectl("get", "secret", f"{cluster_name}-kubeconfig", "-n", cluster_ns,
                        "-o", "jsonpath={.data.value}")
        if r.returncode == 0 and r.stdout.strip():
            import base64
            kubeconfig = base64.b64decode(r.stdout.strip()).decode()
            Path(kubeconfig_path).write_text(kubeconfig)
            result["kubeconfig_path"] = kubeconfig_path

        state["hosted_kubeconfig"] = kubeconfig_path
        state["hosted_cluster_ns"] = cluster_ns
        state["hosted_base_domain"] = base_domain
        save_state(state)

        result["success"] = result["cluster_ready"]

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
