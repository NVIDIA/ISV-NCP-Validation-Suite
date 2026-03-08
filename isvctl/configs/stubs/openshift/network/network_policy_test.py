#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Test NetworkPolicy enforcement across namespaces.

Creates pods in two namespaces, applies a deny NetworkPolicy,
verifies cross-namespace traffic is blocked, then removes the
policy and verifies traffic is allowed again.

Environment:
    K8S_NAMESPACE: Primary namespace (default: ncp-network-validation)

Output schema: generic (fields: policy_enforced, traffic_blocked,
    traffic_allowed_after_delete)
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


def cleanup(ns1: str, ns2: str) -> None:
    """Remove test pods and network policy."""
    run_cmd("kubectl", "delete", "pod", "netpol-server", "-n", ns1,
            "--ignore-not-found", "--grace-period=0", "--force")
    run_cmd("kubectl", "delete", "pod", "netpol-client", "-n", ns2,
            "--ignore-not-found", "--grace-period=0", "--force")
    run_cmd("kubectl", "delete", "networkpolicy", "deny-cross-ns",
            "-n", ns1, "--ignore-not-found")


def main() -> int:
    ns1 = os.environ.get("K8S_NAMESPACE", "ncp-network-validation")
    ns2 = "ncp-network-validation-2"

    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "policy_enforced": False,
        "traffic_blocked": False,
        "traffic_allowed_after_delete": False,
    }

    try:
        # Clean up any leftovers
        cleanup(ns1, ns2)

        # Create server pod in ns1 with a simple HTTP listener
        server_yaml = json.dumps({
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": "netpol-server",
                "namespace": ns1,
                "labels": {"app": "netpol-server"},
            },
            "spec": {
                "containers": [{
                    "name": "server",
                    "image": "registry.access.redhat.com/ubi9/ubi-minimal:latest",
                    "command": [
                        "sh", "-c",
                        "python3 -m http.server 8080 || "
                        "while true; do echo -e 'HTTP/1.1 200 OK\\r\\n\\r\\nOK' "
                        "| nc -l -p 8080 -q 1; done",
                    ],
                    "ports": [{"containerPort": 8080}],
                }],
                "restartPolicy": "Never",
            },
        })
        r = run_cmd("kubectl", "apply", "-f", "-", input=server_yaml)
        if r.returncode != 0:
            # Try with stdin via subprocess directly
            proc = subprocess.run(
                ["kubectl", "apply", "-f", "-"],
                input=server_yaml, capture_output=True, text=True, timeout=120,
            )
            if proc.returncode != 0:
                result["error"] = f"Failed to create server pod: {proc.stderr}"
                print(json.dumps(result, indent=2))
                return 1

        # Create client pod in ns2
        client_yaml = json.dumps({
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": "netpol-client",
                "namespace": ns2,
            },
            "spec": {
                "containers": [{
                    "name": "client",
                    "image": "registry.access.redhat.com/ubi9/ubi-minimal:latest",
                    "command": ["sh", "-c", "sleep 3600"],
                }],
                "restartPolicy": "Never",
            },
        })
        subprocess.run(
            ["kubectl", "apply", "-f", "-"],
            input=client_yaml, capture_output=True, text=True, timeout=120,
        )

        # Wait for pods to be ready
        print("Waiting for pods to become ready...", file=sys.stderr)
        if not wait_for_pod_ready(ns1, "netpol-server"):
            result["error"] = "Server pod did not become ready"
            cleanup(ns1, ns2)
            print(json.dumps(result, indent=2))
            return 1

        if not wait_for_pod_ready(ns2, "netpol-client"):
            result["error"] = "Client pod did not become ready"
            cleanup(ns1, ns2)
            print(json.dumps(result, indent=2))
            return 1

        # Get server pod IP
        r = run_cmd(
            "kubectl", "get", "pod", "netpol-server", "-n", ns1,
            "-o", "jsonpath={.status.podIP}",
        )
        server_ip = r.stdout.strip()
        if not server_ip:
            result["error"] = "Could not get server pod IP"
            cleanup(ns1, ns2)
            print(json.dumps(result, indent=2))
            return 1

        print(f"Server pod IP: {server_ip}", file=sys.stderr)

        # Apply NetworkPolicy to deny all ingress from other namespaces
        netpol_yaml = json.dumps({
            "apiVersion": "networking.k8s.io/v1",
            "kind": "NetworkPolicy",
            "metadata": {
                "name": "deny-cross-ns",
                "namespace": ns1,
            },
            "spec": {
                "podSelector": {"matchLabels": {"app": "netpol-server"}},
                "policyTypes": ["Ingress"],
                "ingress": [{
                    "from": [{
                        "podSelector": {},
                    }],
                }],
            },
        })
        subprocess.run(
            ["kubectl", "apply", "-f", "-"],
            input=netpol_yaml, capture_output=True, text=True, timeout=120,
        )

        # Allow a moment for the policy to be applied
        time.sleep(5)

        # Test that traffic from ns2 is blocked
        print("Testing cross-namespace traffic (should be blocked)...",
              file=sys.stderr)
        r = run_cmd(
            "kubectl", "exec", "netpol-client", "-n", ns2, "--",
            "sh", "-c",
            f"wget -q -O /dev/null --timeout=5 http://{server_ip}:8080/ 2>&1"
            " && echo REACHABLE || echo BLOCKED",
            timeout=30,
        )
        traffic_blocked = "BLOCKED" in r.stdout or r.returncode != 0
        result["traffic_blocked"] = traffic_blocked
        result["policy_enforced"] = traffic_blocked

        if traffic_blocked:
            print("Cross-namespace traffic correctly blocked.", file=sys.stderr)
        else:
            print("WARNING: Traffic was NOT blocked by policy.",
                  file=sys.stderr)

        # Delete the NetworkPolicy
        run_cmd("kubectl", "delete", "networkpolicy", "deny-cross-ns",
                "-n", ns1)
        time.sleep(5)

        # Test that traffic is now allowed
        print("Testing cross-namespace traffic (should be allowed)...",
              file=sys.stderr)
        r = run_cmd(
            "kubectl", "exec", "netpol-client", "-n", ns2, "--",
            "sh", "-c",
            f"wget -q -O /dev/null --timeout=10 http://{server_ip}:8080/ 2>&1"
            " && echo REACHABLE || echo BLOCKED",
            timeout=30,
        )
        traffic_allowed = "REACHABLE" in r.stdout
        result["traffic_allowed_after_delete"] = traffic_allowed

        if traffic_allowed:
            print("Traffic correctly allowed after policy removal.",
                  file=sys.stderr)
        else:
            print("WARNING: Traffic still blocked after policy removal.",
                  file=sys.stderr)

        result["success"] = traffic_blocked and traffic_allowed

    except Exception as e:
        result["error"] = str(e)
    finally:
        cleanup(ns1, ns2)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
