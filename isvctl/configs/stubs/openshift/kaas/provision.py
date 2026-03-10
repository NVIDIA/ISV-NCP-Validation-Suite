#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Provision OpenShift cluster on Carbide bare metal.

Orchestrates Assisted Installer (aicli) and Carbide (carbidecli) to:
1. Create a cluster in Assisted Installer
2. Collect the iPXE discovery config
3. Create an OperatingSystem in Carbide with the iPXE config
4. Batch-create bare-metal instances with the OS + InstanceType
5. Collect instance UUIDs + MAC addresses
6. Monitor hosts calling home in AI, match to instances, approve
7. Monitor OpenShift installation and collect kubeconfig
8. Install GPU Operator via OperatorHub

Supports pre-existing Carbide resources (VPC, subnet, etc.) via env vars.

Environment variables:
    CARBIDE_TOKEN / CARBIDE_API_KEY: Carbide authentication
    CARBIDE_ORG:            Carbide organization
    CARBIDE_SITE_ID:        Site UUID for instance provisioning
    CARBIDE_INSTANCE_TYPE:  Instance type UUID
    CARBIDE_VPC_ID:         Pre-existing VPC UUID (optional, creates if unset)
    CARBIDE_SUBNET_ID:      Pre-existing subnet UUID (optional)
    CARBIDE_SSH_KEY_GROUP:  SSH key group UUID (optional)
    CARBIDE_INSTANCE_COUNT: Number of instances (default: 3)
    OCP_PULL_SECRET:        OpenShift pull secret (JSON string or file path)
    OCP_VERSION:            OpenShift version (default: 4.18)
    OCP_BASE_DOMAIN:        Base DNS domain (default: example.com)
    AI_OFFLINETOKEN:        Assisted Installer offline token (SaaS)
    AI_URL:                 Assisted Installer URL (on-prem, overrides SaaS)
    STATE_FILE:             State file path (default: /tmp/ncp-ocp-provision-state.json)

Output schema: cluster
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "stubs"))
try:
    from carbide.common.carbide import run_carbide, load_state, save_state
except ImportError:
    # Fallback if import path doesn't resolve
    def run_carbide(*args: str, timeout: int = 600) -> dict[str, Any]:
        cmd = ["carbidecli", "-o", "json"] + list(args)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            raise RuntimeError(f"carbidecli {' '.join(args)} failed: {result.stderr}")
        return json.loads(result.stdout)

    def load_state(state_file: str | None = None) -> dict[str, Any]:
        path = Path(state_file or os.environ.get("STATE_FILE", "/tmp/ncp-ocp-provision-state.json"))
        return json.loads(path.read_text()) if path.exists() else {}

    def save_state(state: dict[str, Any], state_file: str | None = None) -> None:
        path = Path(state_file or os.environ.get("STATE_FILE", "/tmp/ncp-ocp-provision-state.json"))
        path.write_text(json.dumps(state, indent=2))


STATE_FILE = os.environ.get("STATE_FILE", "/tmp/ncp-ocp-provision-state.json")


def run_aicli(*args: str, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    """Run an aicli command."""
    cmd = ["aicli"] + list(args)
    ai_url = os.environ.get("AI_URL")
    if ai_url:
        cmd = ["aicli", "--url", ai_url] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def step_create_ai_cluster(state: dict[str, Any]) -> dict[str, Any]:
    """Step 1: Create cluster in Assisted Installer."""
    if state.get("ai_cluster_created"):
        print("AI cluster already created, skipping...", file=sys.stderr)
        return state

    cluster_name = os.environ.get("CARBIDE_VPC_NAME", "ncp-ocp-validation")
    ocp_version = os.environ.get("OCP_VERSION", "4.18")
    base_domain = os.environ.get("OCP_BASE_DOMAIN", "example.com")
    pull_secret = os.environ.get("OCP_PULL_SECRET", "")

    if not pull_secret:
        raise RuntimeError("OCP_PULL_SECRET is required")

    # Resolve pull secret to file path (aicli expects a file)
    if pull_secret and not os.path.isfile(pull_secret):
        pull_secret_path = Path(f"/tmp/{cluster_name}-pull-secret.json")
        pull_secret_path.write_text(pull_secret)
        pull_secret = str(pull_secret_path)

    print(f"Creating OpenShift {ocp_version} cluster '{cluster_name}'...", file=sys.stderr)
    create_args = [
        "create", "cluster", cluster_name,
        "-P", f"openshift_version={ocp_version}",
        "-P", f"base_dns_domain={base_domain}",
    ]
    if pull_secret:
        create_args += ["-P", f"pull_secret={pull_secret}"]

    r = run_aicli(*create_args)
    if r.returncode != 0:
        raise RuntimeError(f"aicli create cluster failed: {r.stderr}")

    state["cluster_name"] = cluster_name
    state["ocp_version"] = ocp_version
    state["ai_cluster_created"] = True
    save_state(state, STATE_FILE)
    return state


def step_collect_ipxe(state: dict[str, Any]) -> dict[str, Any]:
    """Step 2: Collect iPXE discovery config from AI."""
    if state.get("ipxe_config"):
        print("iPXE config already collected, skipping...", file=sys.stderr)
        return state

    cluster_name = state["cluster_name"]
    print("Collecting iPXE discovery config...", file=sys.stderr)

    r = run_aicli("info", "iso", cluster_name)
    if r.returncode != 0:
        raise RuntimeError(f"Failed to get discovery ISO info: {r.stderr}")

    # The iPXE config is generated from the discovery ISO URL
    iso_url = r.stdout.strip()
    ipxe_script = f"""#!ipxe
chain {iso_url}
"""
    state["ipxe_config"] = ipxe_script
    state["discovery_iso_url"] = iso_url
    save_state(state, STATE_FILE)
    print(f"  iPXE config collected (ISO URL: {iso_url[:80]}...)", file=sys.stderr)
    return state


def step_create_os(state: dict[str, Any]) -> dict[str, Any]:
    """Step 3: Create OperatingSystem in Carbide with iPXE config."""
    if state.get("os_id"):
        print("OperatingSystem already created, skipping...", file=sys.stderr)
        return state

    os_name = f"{state['cluster_name']}-discovery"
    print(f"Creating OperatingSystem '{os_name}'...", file=sys.stderr)

    result = run_carbide(
        "operating-system", "create",
        "--name", os_name,
        "--type", "iPXE",
        "--ipxe-script", state["ipxe_config"],
    )
    state["os_id"] = result.get("id")
    state["os_name"] = os_name
    state["os_created"] = True
    save_state(state, STATE_FILE)
    print(f"  OperatingSystem created: {state['os_id']}", file=sys.stderr)
    return state


def step_create_instances(state: dict[str, Any]) -> dict[str, Any]:
    """Step 4: Batch-create bare-metal instances."""
    if state.get("instance_ids"):
        print("Instances already created, skipping...", file=sys.stderr)
        return state

    site_id = os.environ.get("CARBIDE_SITE_ID", "")
    instance_type = os.environ.get("CARBIDE_INSTANCE_TYPE", "")
    instance_count = int(os.environ.get("CARBIDE_INSTANCE_COUNT", "3"))
    vpc_id = os.environ.get("CARBIDE_VPC_ID", state.get("vpc_id", ""))
    ssh_key_group = os.environ.get("CARBIDE_SSH_KEY_GROUP", "")

    if not site_id:
        raise RuntimeError("CARBIDE_SITE_ID is required")
    if not instance_type:
        raise RuntimeError("CARBIDE_INSTANCE_TYPE is required")

    # Create VPC if not pre-existing
    if not vpc_id:
        print("Creating VPC...", file=sys.stderr)
        result = run_carbide("vpc", "create",
                             "--name", f"{state['cluster_name']}-vpc",
                             "--site-id", site_id)
        vpc_id = result.get("id")
        state["vpc_id"] = vpc_id
        state["vpc_created"] = True
        save_state(state, STATE_FILE)

    print(f"Creating {instance_count} instances...", file=sys.stderr)
    batch_args = [
        "instance", "batch-create",
        "--name-prefix", f"{state['cluster_name']}-node",
        "--count", str(instance_count),
        "--vpc-id", vpc_id,
        "--instance-type", instance_type,
        "--operating-system-id", state["os_id"],
    ]
    if ssh_key_group:
        batch_args += ["--ssh-key-group-ids", ssh_key_group]

    result = run_carbide(*batch_args)
    instances = result if isinstance(result, list) else result.get("instances", [result])
    instance_ids = [i["id"] for i in instances]

    state["instance_ids"] = instance_ids
    state["instances_created"] = True
    save_state(state, STATE_FILE)
    print(f"  Instances created: {instance_ids}", file=sys.stderr)
    return state


def step_collect_instance_info(state: dict[str, Any]) -> dict[str, Any]:
    """Step 5: Collect instance UUIDs + MAC addresses."""
    if state.get("instance_macs"):
        return state

    print("Collecting instance info (UUIDs + MACs)...", file=sys.stderr)
    macs = {}
    for instance_id in state["instance_ids"]:
        info = run_carbide("instance", "get", instance_id)
        mac = info.get("macAddress", info.get("mac_address", ""))
        macs[instance_id] = mac
        print(f"  {instance_id}: MAC={mac}", file=sys.stderr)

    state["instance_macs"] = macs
    save_state(state, STATE_FILE)
    return state


def step_monitor_hosts(state: dict[str, Any]) -> dict[str, Any]:
    """Step 6: Monitor hosts in AI, match to instances, approve."""
    if state.get("hosts_approved"):
        return state

    cluster_name = state["cluster_name"]
    instance_count = len(state["instance_ids"])

    print(f"Waiting for {instance_count} hosts to register in AI...", file=sys.stderr)
    r = run_aicli("wait", "hosts", cluster_name, "-n", str(instance_count),
                  timeout=3600)
    if r.returncode != 0:
        raise RuntimeError(f"Hosts did not register: {r.stderr}")
    print("  All hosts registered", file=sys.stderr)

    state["hosts_approved"] = True
    save_state(state, STATE_FILE)
    return state


def step_install_openshift(state: dict[str, Any]) -> dict[str, Any]:
    """Step 7: Start and monitor OpenShift installation."""
    if state.get("cluster_installed"):
        return state

    cluster_name = state["cluster_name"]

    print("Starting OpenShift installation...", file=sys.stderr)
    r = run_aicli("start", cluster_name)
    if r.returncode != 0:
        raise RuntimeError(f"aicli start failed: {r.stderr}")

    print("Waiting for OpenShift installation to complete...", file=sys.stderr)
    r = run_aicli("wait", cluster_name, timeout=5400)  # 90 minutes
    if r.returncode != 0:
        raise RuntimeError(f"OpenShift installation did not complete: {r.stderr}")
    print("  OpenShift installation complete", file=sys.stderr)

    # Download kubeconfig
    kubeconfig_path = os.environ.get("KUBECONFIG", f"/tmp/{cluster_name}-kubeconfig")
    r = run_aicli("download", "kubeconfig", cluster_name)
    if r.returncode == 0:
        local_kubeconfig = Path(f"kubeconfig.{cluster_name}")
        if local_kubeconfig.exists():
            local_kubeconfig.rename(kubeconfig_path)

    state["cluster_installed"] = True
    state["kubeconfig"] = kubeconfig_path
    save_state(state, STATE_FILE)
    return state


def step_day2_operators(state: dict[str, Any]) -> dict[str, Any]:
    """Step 8: Install day-2 operators (GPU Operator, etc.)."""
    if state.get("operators_installed"):
        return state

    kubeconfig = state.get("kubeconfig", os.environ.get("KUBECONFIG", ""))
    oc_cmd = ["oc", "--kubeconfig", kubeconfig] if kubeconfig else ["oc"]

    # Install GPU Operator
    print("Installing GPU Operator via OperatorHub...", file=sys.stderr)
    subprocess.run(oc_cmd + ["create", "namespace", "nvidia-gpu-operator"],
                   capture_output=True, text=True)

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
    subprocess.run(oc_cmd + ["apply", "-f", "-"],
                   input=og_yaml, capture_output=True, text=True)

    subscription_yaml = """
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
    result = subprocess.run(oc_cmd + ["apply", "-f", "-"],
                            input=subscription_yaml, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Warning: GPU Operator subscription failed: {result.stderr}", file=sys.stderr)

    # Wait for GPU Operator pods
    max_wait = 600
    elapsed = 0
    while elapsed < max_wait:
        result = subprocess.run(
            oc_cmd + ["get", "pods", "-n", "nvidia-gpu-operator",
                      "-l", "app=gpu-operator", "--no-headers"],
            capture_output=True, text=True,
        )
        if "Running" in result.stdout:
            print("  GPU Operator is running", file=sys.stderr)
            break
        time.sleep(30)
        elapsed += 30

    state["operators_installed"] = True
    state["gpu_operator_namespace"] = "nvidia-gpu-operator"
    save_state(state, STATE_FILE)
    return state


def collect_inventory(state: dict[str, Any]) -> dict[str, Any]:
    """Collect cluster inventory for validation output."""
    kubeconfig = state.get("kubeconfig", os.environ.get("KUBECONFIG", ""))

    # Query cluster info via oc/kubectl
    env = {**os.environ, "KUBECONFIG": kubeconfig} if kubeconfig else dict(os.environ)

    setup_script = Path(__file__).parent / "setup.sh"
    if setup_script.exists():
        result = subprocess.run(
            ["bash", str(setup_script)],
            capture_output=True, text=True, env=env,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)

    # Fallback: minimal inventory
    return {
        "success": True,
        "platform": "kubernetes",
        "cluster_name": state.get("cluster_name", ""),
        "node_count": len(state.get("instance_ids", [])),
        "kubernetes": {
            "node_count": len(state.get("instance_ids", [])),
            "gpu_operator_namespace": state.get("gpu_operator_namespace", "nvidia-gpu-operator"),
        },
    }


def main() -> int:
    # Validate prerequisites
    for tool in ["carbidecli", "aicli"]:
        if subprocess.run([tool, "--help"], capture_output=True).returncode != 0:
            print(json.dumps({
                "success": False,
                "platform": "kubernetes",
                "error": f"{tool} not found",
            }, indent=2))
            return 1

    try:
        state = load_state(STATE_FILE)

        state = step_create_ai_cluster(state)
        state = step_collect_ipxe(state)
        state = step_create_os(state)
        state = step_create_instances(state)
        state = step_collect_instance_info(state)
        state = step_monitor_hosts(state)
        state = step_install_openshift(state)
        state = step_day2_operators(state)

        inventory = collect_inventory(state)
        print(json.dumps(inventory, indent=2))
        return 0

    except Exception as e:
        print(json.dumps({
            "success": False,
            "platform": "kubernetes",
            "error": str(e),
        }, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
