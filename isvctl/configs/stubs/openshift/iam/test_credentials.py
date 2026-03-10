#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Test Keycloak user credentials via oc login and RBAC checks.

Logs in with the test user, verifies identity, and checks RBAC
grant/deny. Uses a separate kubeconfig to avoid overwriting the
admin session.

Environment:
    KEYCLOAK_NAMESPACE: Namespace for Keycloak (default: ncp-keycloak)
    KEYCLOAK_REALM:     Realm name (default: ncp-validation)
    TEST_USERNAME:      Test user name (default: ncp-test-user)
    TEST_PASSWORD:      Test user password (default: ncp-test-pass)

Output schema: generic (fields: account_id, tests)
"""

import json
import os
import subprocess
import sys
from typing import Any


def run_oc(*args: str, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    cmd = ["oc"] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                          env=env or os.environ)


def main() -> int:
    username = os.environ.get("TEST_USERNAME", "ncp-test-user")
    password = os.environ.get("TEST_PASSWORD", "ncp-test-pass")

    result: dict[str, Any] = {
        "success": False,
        "platform": "iam",
        "account_id": "",
        "tests": {},
    }

    # Get API server
    r = run_oc("whoami", "--show-server")
    if r.returncode != 0:
        result["error"] = "Could not get API server URL"
        print(json.dumps(result, indent=2))
        return 1
    api_server = r.stdout.strip()

    # Login with test user (separate kubeconfig)
    test_kubeconfig = "/tmp/ncp-iam-test-kubeconfig"
    test_env = {**os.environ, "KUBECONFIG": test_kubeconfig}

    r = subprocess.run(
        ["oc", "login", api_server,
         f"--username={username}", f"--password={password}",
         "--insecure-skip-tls-verify"],
        capture_output=True, text=True, timeout=60, env=test_env,
    )

    if r.returncode == 0:
        result["tests"]["identity"] = {"passed": True, "message": f"oc login succeeded as {username}"}

        # Verify identity
        r = subprocess.run(["oc", "whoami"], capture_output=True, text=True, timeout=30, env=test_env)
        if r.returncode == 0:
            identity = r.stdout.strip()
            result["account_id"] = identity
            result["tests"]["access"] = {"passed": identity == username, "message": f"whoami: {identity}"}
        else:
            result["tests"]["access"] = {"passed": False, "message": f"whoami failed: {r.stderr}"}
    else:
        result["tests"]["identity"] = {"passed": False, "message": f"oc login failed: {r.stderr.strip()}"}
        result["tests"]["access"] = {"passed": False, "message": "login failed"}

    # RBAC checks (using admin impersonation)
    r = run_oc("auth", "can-i", "list", "nodes", f"--as={username}")
    denied_nodes = r.stdout.strip() == "no"

    r = run_oc("auth", "can-i", "delete", "namespaces", f"--as={username}")
    denied_ns = r.stdout.strip() == "no"

    result["tests"]["rbac_deny"] = {
        "passed": denied_nodes and denied_ns,
        "message": f"nodes: {'denied' if denied_nodes else 'ALLOWED'}, "
                   f"namespaces: {'denied' if denied_ns else 'ALLOWED'}",
    }

    result["success"] = all(t.get("passed", False) for t in result["tests"].values())

    # Clean up test kubeconfig
    try:
        os.unlink(test_kubeconfig)
    except FileNotFoundError:
        pass

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
