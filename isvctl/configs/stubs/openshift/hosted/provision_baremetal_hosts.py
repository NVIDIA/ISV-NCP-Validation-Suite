#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Provision BareMetalHosts via Carbide for the hosted cluster.

Creates bare-metal instances in Carbide and registers them as
BareMetalHost resources in the management cluster for CAPI to use.

Environment:
    CARBIDE_SITE_ID:       Site UUID
    CARBIDE_INSTANCE_TYPE: Instance type for GPU workers
    HOSTED_WORKER_COUNT:   Number of workers (default: 6)
    HOSTED_CLUSTER_NAME:   Cluster name prefix (default: ncp-hosted)
"""

import json
import os
import subprocess
import sys
import time
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "stubs"))
try:
    from carbide.common.carbide import run_carbide, load_state, save_state
except ImportError:
    def run_carbide(*args: str, timeout: int = 600) -> dict[str, Any]:
        cmd = ["carbidecli", "-o", "json"] + list(args)
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            raise RuntimeError(f"carbidecli failed: {r.stderr}")
        return json.loads(r.stdout)

    def load_state(sf: str | None = None) -> dict[str, Any]:
        p = sf or "/tmp/ncp-hosted-state.json"
        try:
            return json.loads(open(p).read())
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save_state(s: dict[str, Any], sf: str | None = None) -> None:
        p = sf or "/tmp/ncp-hosted-state.json"
        open(p, "w").write(json.dumps(s, indent=2))


STATE_FILE = os.environ.get("HOSTED_STATE_FILE", "/tmp/ncp-hosted-state.json")


def run_kubectl(*args: str, input_data: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["kubectl"] + list(args), capture_output=True, text=True,
                          input=input_data, timeout=120)


def main() -> int:
    site_id = os.environ.get("CARBIDE_SITE_ID", "")
    instance_type = os.environ.get("CARBIDE_INSTANCE_TYPE", "")
    worker_count = int(os.environ.get("HOSTED_WORKER_COUNT", "6"))
    cluster_name = os.environ.get("HOSTED_CLUSTER_NAME", "ncp-hosted")

    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "hosts_ready": 0,
        "host_count": worker_count,
    }

    if not site_id or not instance_type:
        result["error"] = "CARBIDE_SITE_ID and CARBIDE_INSTANCE_TYPE are required"
        print(json.dumps(result, indent=2))
        return 1

    try:
        state = load_state(STATE_FILE)

        if state.get("bmh_instance_ids"):
            print("BareMetalHosts already provisioned.", file=sys.stderr)
            result["hosts_ready"] = len(state["bmh_instance_ids"])
            result["success"] = result["hosts_ready"] >= worker_count
            print(json.dumps(result, indent=2))
            return 0 if result["success"] else 1

        # Batch-create instances in Carbide
        print(f"Provisioning {worker_count} bare-metal instances...", file=sys.stderr)
        batch_result = run_carbide(
            "instance", "batch-create",
            "--name-prefix", f"{cluster_name}-worker",
            "--count", str(worker_count),
            "--site-id", site_id,
            "--instance-type", instance_type,
        )
        instances = batch_result if isinstance(batch_result, list) else batch_result.get("instances", [batch_result])
        instance_ids = [i.get("id", "") for i in instances]

        state["bmh_instance_ids"] = instance_ids
        state["hosted_cluster_name"] = cluster_name
        save_state(state, STATE_FILE)

        # Wait for instances and collect MAC addresses
        print("Waiting for instances to be ready...", file=sys.stderr)
        bmh_data = []
        for iid in instance_ids:
            deadline = time.time() + 1800
            while time.time() < deadline:
                info = run_carbide("instance", "get", iid)
                status = info.get("status", info.get("state", "")).lower()
                if status in ("running", "active", "ready"):
                    bmh_data.append({
                        "instance_id": iid,
                        "mac": info.get("macAddress", info.get("mac_address", "")),
                        "ip": info.get("ip_address", info.get("public_ip", "")),
                        "name": info.get("name", iid),
                    })
                    break
                time.sleep(30)

        state["bmh_data"] = bmh_data
        save_state(state, STATE_FILE)

        # Create BareMetalHost resources in management cluster
        bmh_ns = f"{cluster_name}-hosts"
        run_kubectl("create", "namespace", bmh_ns)

        for bmh in bmh_data:
            bmh_yaml = f"""
apiVersion: metal3.io/v1alpha1
kind: BareMetalHost
metadata:
  name: {bmh['name']}
  namespace: {bmh_ns}
  labels:
    cluster.x-k8s.io/cluster-name: {cluster_name}
spec:
  online: true
  bootMACAddress: "{bmh['mac']}"
  bmc:
    address: "carbide://{bmh['instance_id']}"
    credentialsName: carbide-bmc-secret
"""
            run_kubectl("apply", "-f", "-", input_data=bmh_yaml)

        result["hosts_ready"] = len(bmh_data)
        result["bmh_namespace"] = bmh_ns
        result["success"] = result["hosts_ready"] >= worker_count

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
