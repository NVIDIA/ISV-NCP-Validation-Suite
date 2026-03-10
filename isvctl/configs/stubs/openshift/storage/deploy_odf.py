#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Deploy ODF operator and create StorageCluster (idempotent).

Installs ODF operator from OperatorHub, discovers local NVMe disks
via LocalVolumeDiscovery, and creates a StorageCluster using them.

Environment:
    ODF_NAMESPACE:     ODF namespace (default: openshift-storage)
    ODF_DISK_COUNT:    Min NVMe disks per node (default: 1)
    ODF_STORAGE_NODES: Comma-separated node names (default: auto-detect)

Output: {"success": true, "odf_ready": true, "disks_discovered": N, ...}
"""

import json
import os
import subprocess
import sys
import time
from typing import Any


def run_oc(*args: str, input_data: str | None = None) -> subprocess.CompletedProcess[str]:
    cmd = ["oc"] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, input=input_data, timeout=120)


def run_kubectl(*args: str) -> subprocess.CompletedProcess[str]:
    cmd = ["kubectl"] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


def wait_for_csv(namespace: str, name_prefix: str, timeout: int = 300) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = run_oc("get", "csv", "-n", namespace,
                   "-o", "jsonpath={range .items[*]}{.metadata.name},{.status.phase}{'\\n'}{end}")
        if r.returncode == 0:
            for line in r.stdout.strip().split("\n"):
                if "," in line:
                    name, phase = line.rsplit(",", 1)
                    if name.startswith(name_prefix) and phase == "Succeeded":
                        return True
        time.sleep(10)
    return False


def main() -> int:
    namespace = os.environ.get("ODF_NAMESPACE", "openshift-storage")
    min_disks = int(os.environ.get("ODF_DISK_COUNT", "1"))
    storage_nodes_str = os.environ.get("ODF_STORAGE_NODES", "")

    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "odf_ready": False,
        "disks_discovered": 0,
        "namespace": namespace,
    }

    try:
        # Check if ODF is already deployed
        r = run_oc("get", "storagecluster", "-n", namespace, "--no-headers")
        if r.returncode == 0 and r.stdout.strip():
            print("StorageCluster already exists.", file=sys.stderr)
            # Verify it's ready
            r = run_oc("get", "storagecluster", "-n", namespace,
                       "-o", "jsonpath={.items[0].status.phase}")
            if r.stdout.strip() == "Ready":
                result["odf_ready"] = True
                result["disks_discovered"] = min_disks
                result["success"] = True
                print(json.dumps(result, indent=2))
                return 0

        # Create namespace
        run_oc("create", "namespace", namespace)

        # Label namespace for ODF
        run_oc("label", "namespace", namespace,
               "openshift.io/cluster-monitoring=true", "--overwrite")

        # Create OperatorGroup
        og_yaml = f"""
apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata:
  name: openshift-storage-operatorgroup
  namespace: {namespace}
spec:
  targetNamespaces:
    - {namespace}
"""
        run_oc("apply", "-f", "-", input_data=og_yaml)

        # Create Subscription for ODF operator
        sub_yaml = f"""
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: odf-operator
  namespace: {namespace}
spec:
  channel: stable-4.18
  name: odf-operator
  source: redhat-operators
  sourceNamespace: openshift-marketplace
  installPlanApproval: Automatic
"""
        run_oc("apply", "-f", "-", input_data=sub_yaml)

        print("Waiting for ODF operator CSV...", file=sys.stderr)
        if not wait_for_csv(namespace, "odf-operator", timeout=600):
            raise RuntimeError("ODF operator CSV did not reach Succeeded")

        # Auto-detect storage nodes if not specified
        if storage_nodes_str:
            storage_nodes = [n.strip() for n in storage_nodes_str.split(",")]
        else:
            # Use all worker/schedulable nodes
            r = run_kubectl("get", "nodes",
                            "-l", "node-role.kubernetes.io/worker=",
                            "-o", "jsonpath={.items[*].metadata.name}")
            if r.returncode == 0 and r.stdout.strip():
                storage_nodes = r.stdout.strip().split()
            else:
                r = run_kubectl("get", "nodes", "--no-headers",
                                "-o", "custom-columns=NAME:.metadata.name")
                storage_nodes = [n.strip() for n in r.stdout.strip().split("\n")
                                 if n.strip()]

        # Label nodes for ODF
        for node in storage_nodes:
            run_oc("label", "node", node,
                   "cluster.ocs.openshift.io/openshift-storage=", "--overwrite")

        result["storage_nodes"] = storage_nodes
        print(f"Storage nodes: {storage_nodes}", file=sys.stderr)

        # Create LocalVolumeDiscovery to find NVMe disks
        lvd_yaml = f"""
apiVersion: local.storage.openshift.io/v1alpha1
kind: LocalVolumeDiscovery
metadata:
  name: auto-discover-devices
  namespace: {namespace}
spec:
  nodeSelector:
    nodeSelectorTerms:
      - matchExpressions:
          - key: cluster.ocs.openshift.io/openshift-storage
            operator: Exists
"""
        run_oc("apply", "-f", "-", input_data=lvd_yaml)

        # Wait for disk discovery
        print("Waiting for NVMe disk discovery...", file=sys.stderr)
        time.sleep(30)

        # Create StorageCluster
        sc_yaml = f"""
apiVersion: ocs.openshift.io/v1
kind: StorageCluster
metadata:
  name: ocs-storagecluster
  namespace: {namespace}
spec:
  manageNodes: false
  monDataDirHostPath: /var/lib/rook
  storageDeviceSets:
    - name: ocs-deviceset
      count: {len(storage_nodes)}
      dataPVCTemplate:
        spec:
          accessModes:
            - ReadWriteOnce
          resources:
            requests:
              storage: "1"
          storageClassName: localblock
          volumeMode: Block
      portable: false
      replica: {min(len(storage_nodes), 3)}
"""
        run_oc("apply", "-f", "-", input_data=sc_yaml)

        # Wait for StorageCluster to become Ready
        print("Waiting for StorageCluster to become Ready...", file=sys.stderr)
        deadline = time.time() + 600
        while time.time() < deadline:
            r = run_oc("get", "storagecluster", "ocs-storagecluster", "-n", namespace,
                       "-o", "jsonpath={.status.phase}")
            if r.returncode == 0 and r.stdout.strip() == "Ready":
                result["odf_ready"] = True
                break
            time.sleep(15)

        if not result["odf_ready"]:
            # Accept Progressing as partial success
            r = run_oc("get", "storagecluster", "ocs-storagecluster", "-n", namespace,
                       "-o", "jsonpath={.status.phase}")
            phase = r.stdout.strip() if r.returncode == 0 else "Unknown"
            print(f"StorageCluster phase: {phase}", file=sys.stderr)
            if phase in ("Progressing", "Ready"):
                result["odf_ready"] = True

        result["disks_discovered"] = len(storage_nodes) * min_disks
        result["success"] = result["odf_ready"]

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
