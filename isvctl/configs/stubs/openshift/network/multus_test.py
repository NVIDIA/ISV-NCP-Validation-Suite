#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Test Multus secondary network interface attachment.

Validates:
  - Multus pods are running in the openshift-multus namespace
  - A NetworkAttachmentDefinition can be created (macvlan/bridge)
  - A pod with a secondary network annotation receives multiple
    network interfaces

Environment:
    K8S_NAMESPACE: Test namespace (default: ncp-network-validation)

Output schema: generic (fields: multus_ready,
    secondary_interface_attached)
"""

import json
import os
import subprocess
import sys
import time
from typing import Any


def run_cmd(cmd: str, *args: str, **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [cmd] + list(args), capture_output=True, text=True,
        timeout=kwargs.get("timeout", 120),
    )


def wait_for_pod_ready(namespace: str, name: str, timeout: int = 120) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = run_cmd(
            "kubectl", "get", "pod", name, "-n", namespace,
            "-o", "jsonpath={.status.phase}",
        )
        if r.returncode == 0 and r.stdout.strip() == "Running":
            return True
        time.sleep(5)
    return False


def cleanup(namespace: str) -> None:
    """Remove test pod and NetworkAttachmentDefinition."""
    run_cmd("kubectl", "delete", "pod", "multus-test-pod", "-n", namespace,
            "--ignore-not-found", "--grace-period=0", "--force")
    run_cmd("kubectl", "delete", "net-attach-def", "ncp-bridge-net",
            "-n", namespace, "--ignore-not-found")


def main() -> int:
    namespace = os.environ.get("K8S_NAMESPACE", "ncp-network-validation")

    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "multus_ready": False,
        "secondary_interface_attached": False,
    }

    try:
        # Check Multus pods running in openshift-multus namespace
        r = run_cmd("kubectl", "get", "pods", "-n", "openshift-multus",
                     "-o", "json")
        multus_running = False
        if r.returncode == 0:
            pods = json.loads(r.stdout).get("items", [])
            for pod in pods:
                name = pod.get("metadata", {}).get("name", "")
                phase = pod.get("status", {}).get("phase", "")
                if "multus" in name and phase == "Running":
                    multus_running = True
                    break

        result["multus_ready"] = multus_running
        if not multus_running:
            result["error"] = "Multus pods not found running in openshift-multus namespace."
            print(json.dumps(result, indent=2))
            return 1

        print("Multus pods are running.", file=sys.stderr)

        # Clean up any leftovers
        cleanup(namespace)

        # Create NetworkAttachmentDefinition (bridge CNI)
        nad_manifest = json.dumps({
            "apiVersion": "k8s.cni.cncf.io/v1",
            "kind": "NetworkAttachmentDefinition",
            "metadata": {
                "name": "ncp-bridge-net",
                "namespace": namespace,
            },
            "spec": {
                "config": json.dumps({
                    "cniVersion": "0.3.1",
                    "type": "bridge",
                    "bridge": "ncp-br0",
                    "ipam": {
                        "type": "host-local",
                        "subnet": "10.200.0.0/24",
                        "rangeStart": "10.200.0.10",
                        "rangeEnd": "10.200.0.250",
                    },
                }),
            },
        })
        proc = subprocess.run(
            ["kubectl", "apply", "-f", "-"],
            input=nad_manifest, capture_output=True, text=True, timeout=120,
        )
        if proc.returncode != 0:
            result["error"] = (
                f"Failed to create NetworkAttachmentDefinition: {proc.stderr}"
            )
            print(json.dumps(result, indent=2))
            return 1

        print("NetworkAttachmentDefinition created.", file=sys.stderr)

        # Create pod with secondary network annotation
        pod_manifest = json.dumps({
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": "multus-test-pod",
                "namespace": namespace,
                "annotations": {
                    "k8s.v1.cni.cncf.io/networks": "ncp-bridge-net",
                },
            },
            "spec": {
                "containers": [{
                    "name": "test",
                    "image": "registry.access.redhat.com/ubi9/ubi-minimal:latest",
                    "command": ["sh", "-c", "sleep 3600"],
                }],
                "restartPolicy": "Never",
            },
        })
        proc = subprocess.run(
            ["kubectl", "apply", "-f", "-"],
            input=pod_manifest, capture_output=True, text=True, timeout=120,
        )
        if proc.returncode != 0:
            result["error"] = f"Failed to create test pod: {proc.stderr}"
            cleanup(namespace)
            print(json.dumps(result, indent=2))
            return 1

        # Wait for pod readiness
        print("Waiting for Multus test pod...", file=sys.stderr)
        if not wait_for_pod_ready(namespace, "multus-test-pod"):
            result["error"] = "Multus test pod did not become ready"
            cleanup(namespace)
            print(json.dumps(result, indent=2))
            return 1

        # Verify pod has multiple interfaces
        r = run_cmd(
            "kubectl", "exec", "multus-test-pod", "-n", namespace, "--",
            "sh", "-c", "ip -o link show | wc -l",
        )
        iface_count = 0
        if r.returncode == 0:
            try:
                iface_count = int(r.stdout.strip())
            except ValueError:
                pass

        # At least 3 interfaces expected: lo, eth0 (primary), net1 (secondary)
        secondary_attached = iface_count >= 3
        result["secondary_interface_attached"] = secondary_attached

        if secondary_attached:
            print(
                f"Pod has {iface_count} interfaces (secondary attached).",
                file=sys.stderr,
            )
        else:
            print(
                f"Pod has {iface_count} interface(s); expected >= 3.",
                file=sys.stderr,
            )

        # Also check the network-status annotation for confirmation
        r = run_cmd(
            "kubectl", "get", "pod", "multus-test-pod", "-n", namespace,
            "-o", "jsonpath={.metadata.annotations.k8s\\.v1\\.cni\\.cncf\\.io/network-status}",
        )
        if r.returncode == 0 and r.stdout.strip():
            try:
                net_status = json.loads(r.stdout.strip())
                if len(net_status) >= 2:
                    secondary_attached = True
                    result["secondary_interface_attached"] = True
                    print(
                        f"Network status confirms {len(net_status)} networks.",
                        file=sys.stderr,
                    )
            except (json.JSONDecodeError, TypeError):
                pass

        result["success"] = multus_running and secondary_attached

    except Exception as e:
        result["error"] = str(e)
    finally:
        cleanup(namespace)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
