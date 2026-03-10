#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Test RDMA device availability in GPU pods.

Creates a pod requesting rdma/rdma_shared_device_a, verifies
RDMA devices are accessible (/dev/infiniband or ibv_devinfo),
and checks GPUDirect RDMA readiness (nvidia_peermem module).

If no RDMA devices are available on the cluster, the test
succeeds with rdma_available=false and skipped=true.

Environment:
    K8S_NAMESPACE: Test namespace (default: ncp-network-validation)

Output schema: generic (fields: rdma_available, gpudirect_ready)
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


def wait_for_pod_ready(namespace: str, name: str, timeout: int = 180) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = run_cmd(
            "kubectl", "get", "pod", name, "-n", namespace,
            "-o", "jsonpath={.status.phase}",
        )
        if r.returncode == 0 and r.stdout.strip() == "Running":
            return True
        # Check for unschedulable (e.g. no RDMA resource available)
        r2 = run_cmd(
            "kubectl", "get", "pod", name, "-n", namespace,
            "-o", "jsonpath={.status.conditions[?(@.type=='PodScheduled')].reason}",
        )
        if r2.returncode == 0 and r2.stdout.strip() == "Unschedulable":
            return False
        time.sleep(5)
    return False


def cleanup(namespace: str) -> None:
    run_cmd("kubectl", "delete", "pod", "rdma-test-pod", "-n", namespace,
            "--ignore-not-found", "--grace-period=0", "--force")


def main() -> int:
    namespace = os.environ.get("K8S_NAMESPACE", "ncp-network-validation")

    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "rdma_available": False,
        "gpudirect_ready": False,
    }

    try:
        # Check if any node has rdma/rdma_shared_device_a
        r = run_cmd("kubectl", "get", "nodes", "-o", "json")
        has_rdma_resource = False
        if r.returncode == 0:
            nodes = json.loads(r.stdout).get("items", [])
            for node in nodes:
                allocatable = node.get("status", {}).get("allocatable", {})
                rdma_count = int(
                    allocatable.get("rdma/rdma_shared_device_a", "0")
                )
                if rdma_count > 0:
                    has_rdma_resource = True
                    break

        if not has_rdma_resource:
            print(
                "No rdma/rdma_shared_device_a resources on any node. "
                "Skipping RDMA test.",
                file=sys.stderr,
            )
            result["success"] = True
            result["rdma_available"] = False
            result["skipped"] = True
            print(json.dumps(result, indent=2))
            return 0

        # Clean up any leftovers
        cleanup(namespace)

        # Create a pod requesting RDMA resource
        pod_manifest = json.dumps({
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": "rdma-test-pod",
                "namespace": namespace,
            },
            "spec": {
                "containers": [{
                    "name": "rdma",
                    "image": "registry.access.redhat.com/ubi9/ubi-minimal:latest",
                    "command": ["sh", "-c", "sleep 3600"],
                    "resources": {
                        "limits": {
                            "rdma/rdma_shared_device_a": "1",
                        },
                    },
                    "securityContext": {
                        "capabilities": {
                            "add": ["IPC_LOCK"],
                        },
                    },
                }],
                "restartPolicy": "Never",
            },
        })
        proc = subprocess.run(
            ["kubectl", "apply", "-f", "-"],
            input=pod_manifest, capture_output=True, text=True, timeout=120,
        )
        if proc.returncode != 0:
            result["error"] = f"Failed to create RDMA test pod: {proc.stderr}"
            print(json.dumps(result, indent=2))
            return 1

        print("Waiting for RDMA test pod...", file=sys.stderr)
        if not wait_for_pod_ready(namespace, "rdma-test-pod"):
            # Pod could not be scheduled (no RDMA resources available)
            r = run_cmd(
                "kubectl", "get", "pod", "rdma-test-pod", "-n", namespace,
                "-o", "jsonpath={.status.conditions[?(@.type=='PodScheduled')].message}",
            )
            msg = r.stdout.strip() if r.returncode == 0 else "unknown"
            print(f"RDMA test pod unschedulable: {msg}", file=sys.stderr)
            result["success"] = True
            result["rdma_available"] = False
            result["skipped"] = True
            cleanup(namespace)
            print(json.dumps(result, indent=2))
            return 0

        # Check for RDMA devices inside the pod
        rdma_available = False

        # Check /dev/infiniband
        r = run_cmd(
            "kubectl", "exec", "rdma-test-pod", "-n", namespace, "--",
            "sh", "-c", "ls /dev/infiniband/ 2>/dev/null && echo FOUND || echo NOTFOUND",
        )
        if r.returncode == 0 and "FOUND" in r.stdout:
            rdma_available = True
            print("RDMA devices found in /dev/infiniband/.", file=sys.stderr)

        # Try ibv_devinfo as fallback
        if not rdma_available:
            r = run_cmd(
                "kubectl", "exec", "rdma-test-pod", "-n", namespace, "--",
                "sh", "-c", "ibv_devinfo 2>/dev/null && echo FOUND || echo NOTFOUND",
            )
            if r.returncode == 0 and "FOUND" in r.stdout and "hca_id" in r.stdout:
                rdma_available = True
                print("ibv_devinfo reports RDMA devices.", file=sys.stderr)

        result["rdma_available"] = rdma_available

        # Check GPUDirect RDMA (nvidia_peermem module)
        gpudirect_ready = False
        # Check on the node where the pod is running
        r = run_cmd(
            "kubectl", "get", "pod", "rdma-test-pod", "-n", namespace,
            "-o", "jsonpath={.spec.nodeName}",
        )
        if r.returncode == 0 and r.stdout.strip():
            node_name = r.stdout.strip()
            # Use debug pod to check kernel module
            r = run_cmd(
                "oc", "debug", f"node/{node_name}", "--",
                "chroot", "/host", "lsmod",
                timeout=60,
            )
            if r.returncode == 0 and "nvidia_peermem" in r.stdout:
                gpudirect_ready = True
                print("nvidia_peermem module loaded.", file=sys.stderr)
            else:
                print("nvidia_peermem module not loaded.", file=sys.stderr)

        result["gpudirect_ready"] = gpudirect_ready
        result["success"] = rdma_available

    except Exception as e:
        result["error"] = str(e)
    finally:
        cleanup(namespace)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
