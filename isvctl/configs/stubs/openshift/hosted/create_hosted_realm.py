#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Create a Keycloak realm for the hosted cluster.

Uses the Keycloak instance running on the management cluster
(deployed by iam.yaml) to create a separate realm and OIDC client
for the hosted cluster's OAuth configuration.

Environment:
    KEYCLOAK_NAMESPACE: Keycloak namespace on mgmt cluster (default: ncp-keycloak)
    HOSTED_CLUSTER_NAME: Hosted cluster name (default: ncp-hosted)
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
    return subprocess.run(["oc"] + list(args), capture_output=True, text=True, timeout=60)


def main() -> int:
    namespace = os.environ.get("KEYCLOAK_NAMESPACE", "ncp-keycloak")
    cluster_name = os.environ.get("HOSTED_CLUSTER_NAME", "ncp-hosted")
    realm_name = f"{cluster_name}"

    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "realm_name": realm_name,
        "realm_created": False,
    }

    try:
        # Get Keycloak route
        r = run_oc("get", "routes", "-n", namespace, "-o", "jsonpath={.items[0].spec.host}")
        if r.returncode != 0 or not r.stdout.strip():
            result["error"] = "Keycloak not found. Run iam.yaml first."
            print(json.dumps(result, indent=2))
            return 1
        keycloak_url = f"https://{r.stdout.strip()}"

        # Get admin credentials
        for secret_name in ["ncp-keycloak-initial-admin", "keycloak-initial-admin"]:
            r = run_oc("get", "secret", secret_name, "-n", namespace,
                       "-o", "jsonpath={.data.username}")
            if r.returncode == 0 and r.stdout.strip():
                admin_user = base64.b64decode(r.stdout.strip()).decode()
                r2 = run_oc("get", "secret", secret_name, "-n", namespace,
                            "-o", "jsonpath={.data.password}")
                admin_pass = base64.b64decode(r2.stdout.strip()).decode()
                break
        else:
            result["error"] = "Could not get Keycloak admin credentials"
            print(json.dumps(result, indent=2))
            return 1

        # Get admin token
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        token_url = f"{keycloak_url}/realms/master/protocol/openid-connect/token"
        body = urllib.parse.urlencode({
            "grant_type": "password", "client_id": "admin-cli",
            "username": admin_user, "password": admin_pass,
        }).encode()
        req = urllib.request.Request(token_url, data=body, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        resp = urllib.request.urlopen(req, context=ctx, timeout=30)
        token = json.loads(resp.read().decode())["access_token"]

        # Create realm (idempotent)
        realm_data = json.dumps({"realm": realm_name, "enabled": True}).encode()
        req = urllib.request.Request(
            f"{keycloak_url}/admin/realms", data=realm_data, method="POST")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "application/json")
        try:
            urllib.request.urlopen(req, context=ctx, timeout=30)
            result["realm_created"] = True
        except urllib.error.HTTPError as e:
            if e.code == 409:
                result["realm_created"] = True  # Already exists
            else:
                raise

        result["keycloak_url"] = keycloak_url
        result["success"] = result["realm_created"]

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
