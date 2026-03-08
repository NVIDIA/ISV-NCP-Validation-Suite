#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Check SR-IOV Operator and VF provisioning on OpenShift.

Validates the following:
  - SriovNetworkNodeState CRD exists
  - SR-IOV operator pods are running
  - Virtual Functions (VFs) are configured on GPU nodes
  - SriovNetwork resources exist

Environment:
    SRIOV_NAMESPACE: SR-IOV operator namespace
        (default: openshift-sriov-network-operator)

Output schema: generic (fields: sriov_operator_ready, vf_count,
    sriov_networks)
"""

import json
import subprocess
import sys
from typing import Any


def run_cmd(cmd: str, *args: str, **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [cmd] + list(args), capture_output=True, text=True,
        timeout=kwargs.get("timeout", 120),
    )


def main() -> int:
    sriov_ns = "openshift-sriov-network-operator"

    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "sriov_operator_ready": False,
        "vf_count": 0,
        "sriov_networks": [],
    }

    try:
        # Check SriovNetworkNodeState CRD exists
        r = run_cmd("oc", "get", "sriovnetworknodestates",
                     "-n", sriov_ns, "-o", "json")
        if r.returncode != 0:
            result["error"] = (
                "SriovNetworkNodeState CRD not found. "
                "SR-IOV Operator may not be installed."
            )
            print(json.dumps(result, indent=2))
            return 1

        node_states = json.loads(r.stdout).get("items", [])
        print(
            f"Found {len(node_states)} SriovNetworkNodeState resource(s).",
            file=sys.stderr,
        )

        # Check SR-IOV operator pods running
        r = run_cmd("kubectl", "get", "pods", "-n", sriov_ns, "-o", "json")
        operator_running = False
        if r.returncode == 0:
            pods = json.loads(r.stdout).get("items", [])
            for pod in pods:
                name = pod.get("metadata", {}).get("name", "")
                phase = pod.get("status", {}).get("phase", "")
                if "sriov-network-operator" in name and phase == "Running":
                    operator_running = True
                    break

        result["sriov_operator_ready"] = operator_running
        if operator_running:
            print("SR-IOV operator pod is running.", file=sys.stderr)
        else:
            print("SR-IOV operator pod not found running.", file=sys.stderr)

        # Count VFs configured on GPU nodes
        total_vfs = 0
        for state in node_states:
            interfaces = (
                state.get("status", {}).get("interfaces", [])
            )
            for iface in interfaces:
                num_vfs = iface.get("numVfs", 0)
                total_vfs += num_vfs

        result["vf_count"] = total_vfs
        if total_vfs > 0:
            print(f"Total VFs configured: {total_vfs}", file=sys.stderr)
        else:
            print("No VFs configured on any node.", file=sys.stderr)

        # Check SriovNetwork resources
        r = run_cmd("oc", "get", "sriovnetworks", "-n", sriov_ns, "-o", "json")
        sriov_networks: list[str] = []
        if r.returncode == 0:
            items = json.loads(r.stdout).get("items", [])
            for item in items:
                name = item.get("metadata", {}).get("name", "")
                if name:
                    sriov_networks.append(name)

        result["sriov_networks"] = sriov_networks
        if sriov_networks:
            print(
                f"SriovNetwork resources: {', '.join(sriov_networks)}",
                file=sys.stderr,
            )
        else:
            print("No SriovNetwork resources found.", file=sys.stderr)

        # Success if operator is running (VFs and networks may still
        # be in the process of being configured)
        result["success"] = operator_running

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
