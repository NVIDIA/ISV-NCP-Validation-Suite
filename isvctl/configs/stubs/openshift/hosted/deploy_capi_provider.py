#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Deploy Cluster API Provider for Carbide on management cluster.

Installs the CAPI core components and the Carbide infrastructure
provider. Idempotent — safe to run repeatedly.
"""

import json
import os
import subprocess
import sys
import time
from typing import Any


def run_kubectl(*args: str, input_data: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["kubectl"] + list(args), capture_output=True, text=True,
                          input=input_data, timeout=120)


def run_oc(*args: str, input_data: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["oc"] + list(args), capture_output=True, text=True,
                          input=input_data, timeout=120)


def main() -> int:
    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "capi_installed": False,
        "carbide_provider_installed": False,
    }

    try:
        # Check if CAPI is already installed
        r = run_kubectl("get", "crd", "clusters.cluster.x-k8s.io", "--no-headers")
        if r.returncode == 0:
            print("CAPI CRDs already installed.", file=sys.stderr)
            result["capi_installed"] = True
        else:
            # Install CAPI via clusterctl
            r = subprocess.run(
                ["clusterctl", "init", "--infrastructure", "carbide"],
                capture_output=True, text=True, timeout=300,
            )
            if r.returncode != 0:
                # Fallback: install via manifests
                print("clusterctl not available, installing CAPI via manifests...", file=sys.stderr)

                # Install CAPI core
                capi_ns = "capi-system"
                run_kubectl("create", "namespace", capi_ns)

                # Apply CAPI operator subscription
                sub_yaml = f"""
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: cluster-api-operator
  namespace: {capi_ns}
spec:
  channel: stable
  name: cluster-api-operator
  source: redhat-operators
  sourceNamespace: openshift-marketplace
  installPlanApproval: Automatic
"""
                run_oc("apply", "-f", "-", input_data=sub_yaml)

                # Wait for CAPI CRDs
                print("Waiting for CAPI CRDs...", file=sys.stderr)
                deadline = time.time() + 300
                while time.time() < deadline:
                    r = run_kubectl("get", "crd", "clusters.cluster.x-k8s.io", "--no-headers")
                    if r.returncode == 0:
                        result["capi_installed"] = True
                        break
                    time.sleep(10)
            else:
                result["capi_installed"] = True

        # Check Carbide infrastructure provider
        r = run_kubectl("get", "crd", "carbidemachines.infrastructure.cluster.x-k8s.io",
                        "--no-headers")
        if r.returncode == 0:
            print("Carbide CAPI provider already installed.", file=sys.stderr)
            result["carbide_provider_installed"] = True
        else:
            # Install Carbide infrastructure provider
            carbide_provider_ns = "capc-system"
            run_kubectl("create", "namespace", carbide_provider_ns)

            # Apply Carbide provider manifests
            # The provider is installed via InfrastructureProvider CR
            ip_yaml = f"""
apiVersion: operator.cluster.x-k8s.io/v1alpha2
kind: InfrastructureProvider
metadata:
  name: carbide
  namespace: {carbide_provider_ns}
spec:
  version: v0.1.0
  fetchConfig:
    url: https://github.com/fabiendupont/cluster-api-provider-nvidia-carbide/releases
"""
            run_oc("apply", "-f", "-", input_data=ip_yaml)

            # Wait for Carbide provider CRDs
            print("Waiting for Carbide CAPI provider...", file=sys.stderr)
            deadline = time.time() + 300
            while time.time() < deadline:
                r = run_kubectl("get", "deployment", "-n", carbide_provider_ns, "--no-headers")
                if r.returncode == 0 and r.stdout.strip():
                    result["carbide_provider_installed"] = True
                    break
                time.sleep(10)

        result["success"] = result["capi_installed"]

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
