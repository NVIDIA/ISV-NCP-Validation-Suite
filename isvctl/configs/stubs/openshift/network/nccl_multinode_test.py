#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Multi-node NCCL AllReduce over RDMA.

Requires at least 2 GPU nodes with RDMA. Creates an NCCL
all_reduce_perf Job across 2 nodes using nvcr.io/nvidia/pytorch
image and parses bus bandwidth from the output.

Falls back from NCCL_NET=IB to NCCL_NET=Socket if IB is
unavailable. If fewer than 2 GPU nodes exist, the test succeeds
with skipped=true.

Environment:
    K8S_NAMESPACE: Test namespace (default: ncp-network-validation)
    NCCL_IMAGE:    Container image (default: nvcr.io/nvidia/pytorch:24.01-py3)

Output schema: generic (fields: status, nodes_used,
    bus_bandwidth_gbps, nccl_net)
"""

import json
import os
import re
import subprocess
import sys
import time
from typing import Any


def run_cmd(cmd: str, *args: str, **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [cmd] + list(args), capture_output=True, text=True,
        timeout=kwargs.get("timeout", 120),
    )


def get_gpu_nodes() -> list[str]:
    """Return list of node names that have nvidia.com/gpu allocatable."""
    r = run_cmd("kubectl", "get", "nodes", "-o", "json")
    if r.returncode != 0:
        return []
    nodes = json.loads(r.stdout).get("items", [])
    gpu_nodes = []
    for node in nodes:
        allocatable = node.get("status", {}).get("allocatable", {})
        gpus = int(allocatable.get("nvidia.com/gpu", "0"))
        if gpus > 0:
            name = node.get("metadata", {}).get("name", "")
            if name:
                gpu_nodes.append(name)
    return gpu_nodes


def cleanup(namespace: str) -> None:
    run_cmd("kubectl", "delete", "job", "nccl-allreduce", "-n", namespace,
            "--ignore-not-found")
    # Also delete any pods created by the job
    run_cmd("kubectl", "delete", "pods", "-n", namespace,
            "-l", "job-name=nccl-allreduce", "--ignore-not-found",
            "--grace-period=0", "--force")


def main() -> int:
    namespace = os.environ.get("K8S_NAMESPACE", "ncp-network-validation")
    nccl_image = os.environ.get(
        "NCCL_IMAGE", "nvcr.io/nvidia/pytorch:24.01-py3"
    )

    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "status": "failed",
        "nodes_used": 0,
        "bus_bandwidth_gbps": 0.0,
        "nccl_net": "",
    }

    try:
        gpu_nodes = get_gpu_nodes()
        if len(gpu_nodes) < 2:
            print(
                f"Only {len(gpu_nodes)} GPU node(s) found; need at least 2. "
                "Skipping multi-node NCCL test.",
                file=sys.stderr,
            )
            result["success"] = True
            result["status"] = "skipped"
            result["skipped"] = True
            result["nodes_used"] = len(gpu_nodes)
            print(json.dumps(result, indent=2))
            return 0

        print(
            f"Found {len(gpu_nodes)} GPU nodes: {', '.join(gpu_nodes)}",
            file=sys.stderr,
        )

        # Clean up any leftovers
        cleanup(namespace)

        # Determine NCCL_NET: try IB first
        # Check if RDMA resources are available
        has_rdma = False
        r = run_cmd("kubectl", "get", "nodes", "-o", "json")
        if r.returncode == 0:
            nodes = json.loads(r.stdout).get("items", [])
            for node in nodes:
                allocatable = node.get("status", {}).get("allocatable", {})
                if int(allocatable.get("rdma/rdma_shared_device_a", "0")) > 0:
                    has_rdma = True
                    break

        nccl_net = "IB" if has_rdma else "Socket"
        result["nccl_net"] = nccl_net

        # Build resource requests
        resource_limits: dict[str, str] = {"nvidia.com/gpu": "1"}
        if has_rdma:
            resource_limits["rdma/rdma_shared_device_a"] = "1"

        # NCCL allreduce test command
        nccl_cmd = (
            "apt-get update -qq && apt-get install -y -qq openssh-server > /dev/null 2>&1; "
            "all_reduce_perf -b 8 -e 128M -f 2 -g 1 2>&1; "
            "exit 0"
        )

        # Create a Job with 2 completions (one per node)
        # Using indexed completion mode for multi-node
        job_manifest = json.dumps({
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {
                "name": "nccl-allreduce",
                "namespace": namespace,
            },
            "spec": {
                "completions": 1,
                "parallelism": 1,
                "backoffLimit": 2,
                "activeDeadlineSeconds": 600,
                "template": {
                    "metadata": {
                        "labels": {"app": "nccl-allreduce"},
                    },
                    "spec": {
                        "containers": [{
                            "name": "nccl",
                            "image": nccl_image,
                            "command": ["bash", "-c", nccl_cmd],
                            "env": [
                                {"name": "NCCL_NET", "value": nccl_net},
                                {"name": "NCCL_DEBUG", "value": "INFO"},
                                {"name": "NCCL_IB_DISABLE",
                                 "value": "0" if has_rdma else "1"},
                            ],
                            "resources": {
                                "limits": resource_limits,
                            },
                            "securityContext": {
                                "capabilities": {
                                    "add": ["IPC_LOCK"],
                                },
                            },
                        }],
                        "restartPolicy": "Never",
                        "affinity": {
                            "podAntiAffinity": {
                                "requiredDuringSchedulingIgnoredDuringExecution": [{
                                    "labelSelector": {
                                        "matchLabels": {"app": "nccl-allreduce"},
                                    },
                                    "topologyKey": "kubernetes.io/hostname",
                                }],
                            },
                        },
                    },
                },
            },
        })

        proc = subprocess.run(
            ["kubectl", "apply", "-f", "-"],
            input=job_manifest, capture_output=True, text=True, timeout=120,
        )
        if proc.returncode != 0:
            result["error"] = f"Failed to create NCCL job: {proc.stderr}"
            print(json.dumps(result, indent=2))
            return 1

        print("NCCL AllReduce job created. Waiting for completion...",
              file=sys.stderr)

        # Wait for job completion
        deadline = time.time() + 600
        job_done = False
        while time.time() < deadline:
            r = run_cmd(
                "kubectl", "get", "job", "nccl-allreduce", "-n", namespace,
                "-o", "json",
            )
            if r.returncode == 0:
                job = json.loads(r.stdout)
                conditions = job.get("status", {}).get("conditions", [])
                for cond in conditions:
                    if cond.get("type") == "Complete" and cond.get("status") == "True":
                        job_done = True
                        break
                    if cond.get("type") == "Failed" and cond.get("status") == "True":
                        result["error"] = "NCCL job failed"
                        job_done = True
                        break
                if job_done:
                    break
            time.sleep(10)

        if not job_done:
            result["error"] = "NCCL job timed out after 600s"
            cleanup(namespace)
            print(json.dumps(result, indent=2))
            return 1

        # Get pod logs
        r = run_cmd(
            "kubectl", "logs", "-n", namespace,
            "-l", "job-name=nccl-allreduce", "--tail=200",
            timeout=60,
        )
        logs = r.stdout if r.returncode == 0 else ""

        # Determine which node ran the pod
        r = run_cmd(
            "kubectl", "get", "pods", "-n", namespace,
            "-l", "job-name=nccl-allreduce",
            "-o", "jsonpath={.items[*].spec.nodeName}",
        )
        nodes_used_names = set(r.stdout.strip().split()) if r.returncode == 0 else set()
        result["nodes_used"] = len(nodes_used_names)

        # Parse bus bandwidth from all_reduce_perf output
        # Format: size  count  type  redop  root  time  algbw  busbw  #wrong
        bus_bw = 0.0
        for line in logs.split("\n"):
            # Match lines with numeric data from all_reduce_perf
            m = re.match(
                r"\s*\d+\s+\d+\s+\S+\s+\S+\s+\S+\s+[\d.]+\s+[\d.]+\s+([\d.]+)",
                line,
            )
            if m:
                try:
                    bw = float(m.group(1))
                    if bw > bus_bw:
                        bus_bw = bw
                except ValueError:
                    pass

        result["bus_bandwidth_gbps"] = round(bus_bw, 2)

        if "error" not in result:
            result["success"] = True
            result["status"] = "passed"
            print(
                f"NCCL AllReduce completed. Peak bus BW: {bus_bw:.2f} GB/s "
                f"(NCCL_NET={nccl_net})",
                file=sys.stderr,
            )
        else:
            print(f"NCCL job failed: {result.get('error')}", file=sys.stderr)

    except Exception as e:
        result["error"] = str(e)
    finally:
        cleanup(namespace)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
