#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Clean up test user from Keycloak. Keycloak itself stays deployed.

Deletes the test user from the Keycloak realm and cleans up
any OpenShift identity/user objects. Does NOT remove Keycloak,
the operator, or the OAuth IdP configuration.

Environment:
    KEYCLOAK_NAMESPACE: Namespace for Keycloak (default: ncp-keycloak)
    KEYCLOAK_REALM:     Realm name (default: ncp-validation)
    TEST_USERNAME:      Test user name (default: ncp-test-user)

Output schema: teardown
"""

import base64
import json
import os
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def run_oc(*args: str) -> subprocess.CompletedProcess[str]:
    cmd = ["oc"] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)


def main() -> int:
    namespace = os.environ.get("KEYCLOAK_NAMESPACE", "ncp-keycloak")
    realm_name = os.environ.get("KEYCLOAK_REALM", "ncp-validation")
    username = os.environ.get("TEST_USERNAME", "ncp-test-user")

    result: dict[str, Any] = {
        "success": False,
        "platform": "iam",
        "resources_deleted": [],
    }

    try:
        # Get Keycloak route
        r = run_oc("get", "routes", "-n", namespace, "-o", "jsonpath={.items[0].spec.host}")
        if r.returncode != 0 or not r.stdout.strip():
            result["success"] = True
            result["message"] = "Keycloak not found, nothing to clean up"
            print(json.dumps(result, indent=2))
            return 0
        keycloak_url = f"https://{r.stdout.strip()}"

        # Get admin token
        admin_user = admin_pass = ""
        for secret_name in ["ncp-keycloak-initial-admin", "keycloak-initial-admin"]:
            r = run_oc("get", "secret", secret_name, "-n", namespace,
                       "-o", "jsonpath={.data.username}")
            if r.returncode == 0 and r.stdout.strip():
                admin_user = base64.b64decode(r.stdout.strip()).decode()
                r2 = run_oc("get", "secret", secret_name, "-n", namespace,
                            "-o", "jsonpath={.data.password}")
                admin_pass = base64.b64decode(r2.stdout.strip()).decode()
                break

        if not admin_user:
            result["success"] = True
            result["message"] = "No admin credentials found, skipping user cleanup"
            print(json.dumps(result, indent=2))
            return 0

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        # Get admin token
        token_url = f"{keycloak_url}/realms/master/protocol/openid-connect/token"
        body = urllib.parse.urlencode({
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": admin_user,
            "password": admin_pass,
        }).encode()
        req = urllib.request.Request(token_url, data=body, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        resp = urllib.request.urlopen(req, context=ctx, timeout=30)
        token = json.loads(resp.read().decode())["access_token"]

        # Find and delete user
        req = urllib.request.Request(
            f"{keycloak_url}/admin/realms/{realm_name}/users?username={username}",
            method="GET")
        req.add_header("Authorization", f"Bearer {token}")
        resp = urllib.request.urlopen(req, context=ctx, timeout=30)
        users = json.loads(resp.read().decode())

        if users:
            user_id = users[0]["id"]
            req = urllib.request.Request(
                f"{keycloak_url}/admin/realms/{realm_name}/users/{user_id}",
                method="DELETE")
            req.add_header("Authorization", f"Bearer {token}")
            urllib.request.urlopen(req, context=ctx, timeout=30)
            result["resources_deleted"].append(f"keycloak-user/{username}")

    except Exception as e:
        # Non-fatal — user may already be deleted
        print(f"Warning: {e}", file=sys.stderr)

    # Clean up OpenShift identity/user objects
    run_oc("delete", "identity", f"ncp-keycloak:{username}", "--ignore-not-found")
    result["resources_deleted"].append(f"identity/ncp-keycloak:{username}")

    run_oc("delete", "user", username, "--ignore-not-found")
    result["resources_deleted"].append(f"user/{username}")

    result["success"] = True
    result["message"] = "Test user cleaned up; Keycloak still deployed"

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
