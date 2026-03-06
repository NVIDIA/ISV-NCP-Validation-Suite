#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Deprovision OpenShift cluster and Carbide infrastructure.

Reverses provisioning in order:
1. Delete OpenShift cluster via aicli
2. Delete instances via carbidecli
3. Delete OperatingSystem via carbidecli
4. Delete VPC via carbidecli (only if created by provision.py)

Environment variables:
    TEARDOWN_ENABLED: Must be "true" to actually delete resources
    STATE_FILE:       Path to state file (default: /tmp/ncp-ocp-provision-state.json)
    AI_URL:           Assisted Installer URL (for on-prem)

Output schema: teardown
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


STATE_FILE = os.environ.get("STATE_FILE", "/tmp/ncp-ocp-provision-state.json")


def run_carbide(*args: str) -> subprocess.CompletedProcess[str]:
    """Run a carbidecli command."""
    cmd = ["carbidecli", "-o", "json"] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=600)


def run_aicli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run an aicli command."""
    cmd = ["aicli"] + list(args)
    ai_url = os.environ.get("AI_URL")
    if ai_url:
        cmd = ["aicli", "--url", ai_url] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=300)


def load_state() -> dict[str, Any]:
    path = Path(STATE_FILE)
    return json.loads(path.read_text()) if path.exists() else {}


def main() -> int:
    teardown_enabled = os.environ.get("TEARDOWN_ENABLED", "false").lower() == "true"
    result: dict[str, Any] = {
        "success": False,
        "platform": "kubernetes",
        "resources_deleted": [],
    }

    if not teardown_enabled:
        result["success"] = True
        result["skipped"] = True
        result["message"] = "Teardown skipped (TEARDOWN_ENABLED != true)"
        print(json.dumps(result, indent=2))
        return 0

    state = load_state()
    if not state:
        result["success"] = True
        result["message"] = "No provisioning state found"
        print(json.dumps(result, indent=2))
        return 0

    errors = []

    # 1. Delete OpenShift cluster via aicli
    cluster_name = state.get("cluster_name")
    if cluster_name and state.get("cluster_installed"):
        print(f"Deleting OpenShift cluster '{cluster_name}'...", file=sys.stderr)
        r = run_aicli("delete", "cluster", cluster_name)
        if r.returncode == 0:
            result["resources_deleted"].append("cluster")
        else:
            errors.append(f"cluster: {r.stderr}")

    # 2. Delete instances (only if we created them)
    if state.get("instances_created") and state.get("instance_ids"):
        print(f"Deleting {len(state['instance_ids'])} instances...", file=sys.stderr)
        for instance_id in state["instance_ids"]:
            r = run_carbide("instance", "delete", instance_id)
            if r.returncode == 0:
                print(f"  Deleted instance {instance_id}", file=sys.stderr)
            else:
                errors.append(f"instance/{instance_id}: {r.stderr}")
        result["resources_deleted"].append("instances")

    # 3. Delete OperatingSystem (only if we created it)
    if state.get("os_created") and state.get("os_id"):
        print(f"Deleting OperatingSystem {state['os_id']}...", file=sys.stderr)
        r = run_carbide("operating-system", "delete", state["os_id"])
        if r.returncode == 0:
            result["resources_deleted"].append("operating-system")
        else:
            errors.append(f"operating-system: {r.stderr}")

    # 4. Delete VPC (only if we created it)
    if state.get("vpc_created") and state.get("vpc_id"):
        print(f"Deleting VPC {state['vpc_id']}...", file=sys.stderr)
        r = run_carbide("vpc", "delete", state["vpc_id"])
        if r.returncode == 0:
            result["resources_deleted"].append("vpc")
        else:
            errors.append(f"vpc: {r.stderr}")

    # Clean up state file
    Path(STATE_FILE).unlink(missing_ok=True)

    if errors:
        result["errors"] = errors
        result["success"] = False
    else:
        result["success"] = True

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
