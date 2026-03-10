#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Tear down the hosted cluster and BareMetalHosts.

Deletes the CAPI Cluster CR (which triggers hosted cluster deletion),
then deletes BareMetalHost resources and terminates Carbide instances.

Gated by TEARDOWN_ENABLED=true to prevent accidental deletion.

Environment:
    TEARDOWN_ENABLED:    Must be "true" to delete resources
    HOSTED_STATE_FILE:   Path to state file (default: /tmp/ncp-hosted-state.json)
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

STATE_FILE = os.environ.get("HOSTED_STATE_FILE", "/tmp/ncp-hosted-state.json")


def load_state() -> dict[str, Any]:
    try:
        return json.loads(Path(STATE_FILE).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def run_kubectl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["kubectl"] + list(args), capture_output=True, text=True, timeout=120)


def run_carbide(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["carbidecli", "-o", "json"] + list(args),
                          capture_output=True, text=True, timeout=600)


def main() -> int:
    teardown_enabled = os.environ.get("TEARDOWN_ENABLED", "false").lower() == "true"

    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "resources_deleted": [],
    }

    if not teardown_enabled:
        result["success"] = True
        result["skipped"] = True
        result["message"] = "Hosted cluster preserved (TEARDOWN_ENABLED != true)"
        print(json.dumps(result, indent=2))
        return 0

    state = load_state()
    cluster_name = state.get("hosted_cluster_name", "ncp-hosted")
    cluster_ns = state.get("hosted_cluster_ns", cluster_name)
    errors = []

    # Delete CAPI Cluster (triggers hosted cluster deletion)
    print("Deleting hosted cluster...", file=sys.stderr)
    r = run_kubectl("delete", "cluster", cluster_name, "-n", cluster_ns, "--ignore-not-found")
    if r.returncode == 0:
        result["resources_deleted"].append(f"cluster/{cluster_name}")

    # Wait for cluster resources to be cleaned up
    time.sleep(30)

    # Delete BareMetalHosts
    bmh_ns = f"{cluster_name}-hosts"
    r = run_kubectl("delete", "baremetalhost", "--all", "-n", bmh_ns, "--ignore-not-found")
    if r.returncode == 0:
        result["resources_deleted"].append(f"baremetalhosts/{bmh_ns}")

    # Delete Carbide instances
    for iid in state.get("bmh_instance_ids", []):
        r = run_carbide("instance", "delete", iid)
        if r.returncode == 0:
            result["resources_deleted"].append(f"instance/{iid}")
        else:
            errors.append(f"instance/{iid}: {r.stderr}")

    # Delete namespaces
    for ns in [cluster_ns, bmh_ns]:
        run_kubectl("delete", "namespace", ns, "--ignore-not-found")
        result["resources_deleted"].append(f"namespace/{ns}")

    # Clean up kubeconfig and state
    kubeconfig = state.get("hosted_kubeconfig", "")
    if kubeconfig:
        Path(kubeconfig).unlink(missing_ok=True)
    Path(STATE_FILE).unlink(missing_ok=True)

    if errors:
        result["errors"] = errors
    result["success"] = len(errors) == 0

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
