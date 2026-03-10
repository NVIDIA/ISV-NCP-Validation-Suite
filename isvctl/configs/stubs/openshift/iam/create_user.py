#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Deploy Keycloak (idempotent) and create a test user.

Ensures the Red Hat Build of Keycloak (RHBK) operator is installed,
a Keycloak instance is running, the OAuth IdP is configured, and a
test user exists in the validation realm.

All steps are idempotent — safe to run repeatedly.

Environment:
    KEYCLOAK_NAMESPACE: Namespace for Keycloak (default: ncp-keycloak)
    KEYCLOAK_REALM:     Realm name (default: ncp-validation)
    TEST_USERNAME:      Test user name (default: ncp-test-user)
    TEST_PASSWORD:      Test user password (default: ncp-test-pass)

Output schema: generic (fields: username, access_key_id)
"""

import base64
import json
import os
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def run_oc(*args: str, input_data: str | None = None) -> subprocess.CompletedProcess[str]:
    cmd = ["oc"] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, input=input_data, timeout=120)


def wait_for_deployment(namespace: str, name: str, timeout: int = 300) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = run_oc("get", "deployment", name, "-n", namespace,
                   "-o", "jsonpath={.status.availableReplicas}")
        if r.returncode == 0 and r.stdout.strip():
            try:
                if int(r.stdout.strip()) > 0:
                    return True
            except ValueError:
                pass
        time.sleep(10)
    return False


def wait_for_csv(namespace: str, name_prefix: str, timeout: int = 300) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = run_oc("get", "csv", "-n", namespace,
                   "-o", "jsonpath={range .items[*]}{.metadata.name},{.status.phase}{'\\n'}{end}")
        if r.returncode == 0:
            for line in r.stdout.strip().split("\n"):
                if "," in line:
                    csv_name, phase = line.rsplit(",", 1)
                    if csv_name.startswith(name_prefix) and phase == "Succeeded":
                        return True
        time.sleep(10)
    return False


def keycloak_api(url: str, token: str, method: str = "GET",
                 data: dict | None = None) -> tuple[int, str]:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    try:
        resp = urllib.request.urlopen(req, context=ctx, timeout=30)
        return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def get_admin_token(keycloak_url: str, username: str, password: str) -> str:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    token_url = f"{keycloak_url}/realms/master/protocol/openid-connect/token"
    body = urllib.parse.urlencode({
        "grant_type": "password",
        "client_id": "admin-cli",
        "username": username,
        "password": password,
    }).encode()
    req = urllib.request.Request(token_url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    resp = urllib.request.urlopen(req, context=ctx, timeout=30)
    return json.loads(resp.read().decode())["access_token"]


def ensure_operator(namespace: str) -> None:
    """Ensure RHBK operator is installed (idempotent)."""
    # Check if already installed
    r = run_oc("get", "csv", "-n", namespace, "--no-headers")
    if r.returncode == 0 and "rhbk-operator" in r.stdout:
        print("RHBK operator already installed.", file=sys.stderr)
        return

    # Create namespace
    run_oc("create", "namespace", namespace)

    # OperatorGroup
    og_yaml = f"""
apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata:
  name: rhbk-operator-group
  namespace: {namespace}
spec:
  targetNamespaces:
    - {namespace}
"""
    run_oc("apply", "-f", "-", input_data=og_yaml)

    # Subscription (Red Hat operator from redhat-operators catalog)
    sub_yaml = f"""
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: rhbk-operator
  namespace: {namespace}
spec:
  channel: stable-v26
  name: rhbk-operator
  source: redhat-operators
  sourceNamespace: openshift-marketplace
  installPlanApproval: Automatic
"""
    run_oc("apply", "-f", "-", input_data=sub_yaml)

    print("Waiting for RHBK operator CSV...", file=sys.stderr)
    if not wait_for_csv(namespace, "rhbk-operator", timeout=300):
        raise RuntimeError("RHBK operator CSV did not reach Succeeded")

    print("Waiting for operator deployment...", file=sys.stderr)
    if not wait_for_deployment(namespace, "rhbk-operator", timeout=120):
        raise RuntimeError("RHBK operator deployment not available")

    print("RHBK operator installed.", file=sys.stderr)


def ensure_keycloak(namespace: str) -> str:
    """Ensure Keycloak instance is running (idempotent). Returns route URL."""
    # Check if already running
    r = run_oc("get", "keycloak", "ncp-keycloak", "-n", namespace, "--no-headers")
    if r.returncode == 0:
        print("Keycloak instance already exists.", file=sys.stderr)
    else:
        kc_yaml = f"""
apiVersion: k8s.keycloak.org/v2alpha1
kind: Keycloak
metadata:
  name: ncp-keycloak
  namespace: {namespace}
spec:
  instances: 1
  http:
    httpEnabled: true
  hostname:
    strict: false
  proxy:
    headers: xforwarded
  additionalOptions:
    - name: http-enabled
      value: "true"
    - name: hostname-strict
      value: "false"
    - name: hostname-strict-https
      value: "false"
"""
        run_oc("apply", "-f", "-", input_data=kc_yaml)

    # Wait for pods
    print("Waiting for Keycloak pods...", file=sys.stderr)
    deadline = time.time() + 300
    while time.time() < deadline:
        r = run_oc("get", "pods", "-n", namespace, "--no-headers")
        if r.returncode == 0:
            for line in r.stdout.strip().split("\n"):
                parts = line.split()
                if len(parts) >= 3 and "ncp-keycloak" in parts[0] and "operator" not in parts[0] and parts[2] == "Running":
                    break
            else:
                time.sleep(10)
                continue
            break
        time.sleep(10)

    # Ensure route exists (edge termination)
    route_yaml = f"""
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: keycloak
  namespace: {namespace}
spec:
  to:
    kind: Service
    name: ncp-keycloak-service
  port:
    targetPort: http
  tls:
    termination: edge
    insecureEdgeTerminationPolicy: Redirect
"""
    run_oc("apply", "-f", "-", input_data=route_yaml)

    # Get route URL
    deadline = time.time() + 60
    while time.time() < deadline:
        r = run_oc("get", "routes", "-n", namespace, "-o", "jsonpath={.items[0].spec.host}")
        if r.returncode == 0 and r.stdout.strip():
            return f"https://{r.stdout.strip()}"
        time.sleep(5)

    raise RuntimeError("Could not get Keycloak route URL")


def ensure_realm(keycloak_url: str, token: str, realm_name: str) -> None:
    """Ensure realm exists (idempotent)."""
    status, _ = keycloak_api(f"{keycloak_url}/admin/realms/{realm_name}", token)
    if status == 200:
        print(f"Realm '{realm_name}' already exists.", file=sys.stderr)
        return

    realm_data = {"realm": realm_name, "enabled": True}
    status, body = keycloak_api(f"{keycloak_url}/admin/realms", token, method="POST", data=realm_data)
    if status not in (201, 409):
        raise RuntimeError(f"Failed to create realm: {status} {body}")
    print(f"Realm '{realm_name}' created.", file=sys.stderr)


def ensure_client(keycloak_url: str, token: str, realm_name: str) -> str:
    """Ensure OpenShift OIDC client exists. Returns client secret."""
    # Check if client exists
    status, body = keycloak_api(
        f"{keycloak_url}/admin/realms/{realm_name}/clients?clientId=openshift", token)
    if status == 200:
        clients = json.loads(body)
        if clients:
            client_uuid = clients[0]["id"]
            # Get existing secret
            status, body = keycloak_api(
                f"{keycloak_url}/admin/realms/{realm_name}/clients/{client_uuid}/client-secret", token)
            if status == 200:
                return json.loads(body).get("value", "")

    # Get apps domain for redirect URI
    r = run_oc("get", "ingress.config.openshift.io", "cluster", "-o", "jsonpath={.spec.domain}")
    apps_domain = r.stdout.strip() if r.returncode == 0 else ""
    redirect_uri = f"https://oauth-openshift.{apps_domain}/oauth2callback/ncp-keycloak" if apps_domain else "*"

    client_data = {
        "clientId": "openshift",
        "enabled": True,
        "protocol": "openid-connect",
        "publicClient": False,
        "directAccessGrantsEnabled": True,
        "standardFlowEnabled": True,
        "redirectUris": [redirect_uri],
    }
    status, body = keycloak_api(
        f"{keycloak_url}/admin/realms/{realm_name}/clients", token, method="POST", data=client_data)
    if status not in (201, 409):
        raise RuntimeError(f"Failed to create client: {status} {body}")

    # Get client UUID and secret
    status, body = keycloak_api(
        f"{keycloak_url}/admin/realms/{realm_name}/clients?clientId=openshift", token)
    clients = json.loads(body)
    client_uuid = clients[0]["id"]
    status, body = keycloak_api(
        f"{keycloak_url}/admin/realms/{realm_name}/clients/{client_uuid}/client-secret", token)
    return json.loads(body).get("value", "") if status == 200 else ""


def ensure_oauth(keycloak_url: str, realm_name: str, client_secret: str,
                 namespace: str) -> None:
    """Ensure OpenShift OAuth is configured with Keycloak IdP (idempotent)."""
    # Check if already configured
    r = run_oc("get", "oauth", "cluster", "-o", "json")
    if r.returncode == 0:
        oauth = json.loads(r.stdout)
        idps = oauth.get("spec", {}).get("identityProviders") or []
        if any(idp.get("name") == "ncp-keycloak" for idp in idps):
            print("OAuth IdP already configured.", file=sys.stderr)
            return

    # Get ingress CA for TLS verification
    r = run_oc("get", "secret", "router-ca", "-n", "openshift-ingress-operator",
               "-o", "jsonpath={.data.tls\\.crt}")
    ingress_ca = ""
    if r.returncode == 0 and r.stdout.strip():
        ingress_ca = base64.b64decode(r.stdout.strip()).decode()

    if ingress_ca:
        ca_cm_yaml = "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: ncp-keycloak-ca\n  namespace: openshift-config\ndata:\n  ca.crt: |\n"
        for line in ingress_ca.strip().split("\n"):
            ca_cm_yaml += f"    {line}\n"
        run_oc("apply", "-f", "-", input_data=ca_cm_yaml)

    # Client secret
    secret_yaml = f"""
apiVersion: v1
kind: Secret
metadata:
  name: ncp-keycloak-client-secret
  namespace: openshift-config
type: Opaque
stringData:
  clientSecret: "{client_secret}"
"""
    run_oc("apply", "-f", "-", input_data=secret_yaml)

    # Patch OAuth CR
    r = run_oc("get", "oauth", "cluster", "-o", "json")
    oauth = json.loads(r.stdout)
    idps = oauth.get("spec", {}).get("identityProviders") or []
    idps = [idp for idp in idps if idp.get("name") != "ncp-keycloak"]

    issuer = f"{keycloak_url}/realms/{realm_name}"
    openid_config: dict[str, Any] = {
        "clientID": "openshift",
        "clientSecret": {"name": "ncp-keycloak-client-secret"},
        "issuer": issuer,
        "claims": {
            "preferredUsername": ["preferred_username"],
            "name": ["name"],
            "email": ["email"],
        },
    }
    if ingress_ca:
        openid_config["ca"] = {"name": "ncp-keycloak-ca"}

    idps.append({
        "name": "ncp-keycloak",
        "type": "OpenID",
        "mappingMethod": "claim",
        "openID": openid_config,
    })

    patch = json.dumps({"spec": {"identityProviders": idps}})
    r = run_oc("patch", "oauth", "cluster", "--type=merge", f"-p={patch}")
    if r.returncode != 0:
        raise RuntimeError(f"Failed to patch OAuth: {r.stderr}")

    # Wait for auth operator to stabilize
    print("Waiting for authentication operator...", file=sys.stderr)
    time.sleep(10)
    deadline = time.time() + 300
    while time.time() < deadline:
        r = run_oc("get", "clusteroperator", "authentication",
                   "-o", "jsonpath={.status.conditions[?(@.type=='Available')].status}")
        if r.returncode == 0 and r.stdout.strip() == "True":
            r2 = run_oc("get", "clusteroperator", "authentication",
                        "-o", "jsonpath={.status.conditions[?(@.type=='Progressing')].status}")
            if r2.returncode == 0 and r2.stdout.strip() == "False":
                break
        time.sleep(15)

    print("OAuth configured with Keycloak IdP.", file=sys.stderr)


def create_keycloak_user(keycloak_url: str, token: str, realm_name: str,
                         username: str, password: str) -> str:
    """Create user in Keycloak realm. Returns user ID."""
    # Check if user exists
    status, body = keycloak_api(
        f"{keycloak_url}/admin/realms/{realm_name}/users?username={username}", token)
    if status == 200:
        users = json.loads(body)
        if users:
            user_id = users[0]["id"]
            # Update password
            keycloak_api(
                f"{keycloak_url}/admin/realms/{realm_name}/users/{user_id}/reset-password",
                token, method="PUT",
                data={"type": "password", "value": password, "temporary": False})
            print(f"User '{username}' already exists, password updated.", file=sys.stderr)
            return user_id

    # Create user
    user_data = {
        "username": username,
        "enabled": True,
        "credentials": [{"type": "password", "value": password, "temporary": False}],
    }
    status, body = keycloak_api(
        f"{keycloak_url}/admin/realms/{realm_name}/users", token, method="POST", data=user_data)
    if status not in (201, 409):
        raise RuntimeError(f"Failed to create user: {status} {body}")

    # Get user ID
    status, body = keycloak_api(
        f"{keycloak_url}/admin/realms/{realm_name}/users?username={username}", token)
    users = json.loads(body)
    user_id = users[0]["id"] if users else ""
    print(f"User '{username}' created.", file=sys.stderr)
    return user_id


def main() -> int:
    namespace = os.environ.get("KEYCLOAK_NAMESPACE", "ncp-keycloak")
    realm_name = os.environ.get("KEYCLOAK_REALM", "ncp-validation")
    username = os.environ.get("TEST_USERNAME", "ncp-test-user")
    password = os.environ.get("TEST_PASSWORD", "ncp-test-pass")

    result: dict[str, Any] = {
        "success": False,
        "platform": "iam",
        "username": username,
    }

    try:
        # Step 1: Ensure operator + Keycloak instance
        ensure_operator(namespace)
        keycloak_url = ensure_keycloak(namespace)
        result["keycloak_url"] = keycloak_url

        # Step 2: Get admin credentials
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
            raise RuntimeError("Could not get Keycloak admin credentials")

        token = get_admin_token(keycloak_url, admin_user, admin_pass)

        # Step 3: Ensure realm + client
        ensure_realm(keycloak_url, token, realm_name)
        client_secret = ensure_client(keycloak_url, token, realm_name)

        # Step 4: Configure OAuth (idempotent)
        ensure_oauth(keycloak_url, realm_name, client_secret, namespace)

        # Step 5: Create test user
        user_id = create_keycloak_user(keycloak_url, token, realm_name, username, password)
        result["access_key_id"] = user_id
        result["user_id"] = user_id
        result["success"] = True

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
