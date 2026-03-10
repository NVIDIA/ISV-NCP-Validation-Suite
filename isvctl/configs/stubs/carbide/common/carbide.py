# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Shared helpers for Carbide CLI (carbidecli) stub scripts.

Provides:
  - run_carbide(): Execute carbidecli commands with JSON output parsing
  - timed_call(): Same as run_carbide but also returns latency
  - load_state() / save_state(): Persist data between steps via JSON file
  - get_scopes(): Parse TARGET_SCOPES env var into structured dict
  - check_scopes(): Verify required scopes are present

Environment:
  carbidecli handles authentication via its own config (~/.carbide/config.yaml)
  or environment variables (CARBIDE_TOKEN, CARBIDE_API_KEY, CARBIDE_ORG, etc.).
  TARGET_SCOPES contains the list of granted API scopes.
"""

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any


DEFAULT_STATE_FILE = "/tmp/ncp-carbide-state.json"


def run_carbide(*args: str, timeout: int = 120) -> dict[str, Any]:
    """Run a carbidecli command and return parsed JSON output.

    Args:
        *args: Command arguments (e.g., "tenant", "get")
        timeout: Command timeout in seconds

    Returns:
        Parsed JSON output from carbidecli

    Raises:
        RuntimeError: If the command fails or returns non-JSON output
    """
    cmd = ["carbidecli", "-o", "json"] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    if result.returncode != 0:
        raise RuntimeError(f"carbidecli {' '.join(args)} failed: {result.stderr.strip()}")

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"carbidecli returned non-JSON output: {result.stdout[:500]}")


def timed_call(*args: str, timeout: int = 120) -> tuple[dict[str, Any], float]:
    """Run a carbidecli command and return (result, latency_seconds)."""
    start = time.monotonic()
    data = run_carbide(*args, timeout=timeout)
    elapsed = time.monotonic() - start
    return data, elapsed


def get_scopes() -> dict[str, set[str]]:
    """Parse TARGET_SCOPES env var into {resource: {read, write}} dict.

    Example:
        TARGET_SCOPES="forge:read_vpc forge:write_vpc forge:read_tenant"
        → {"vpc": {"read", "write"}, "tenant": {"read"}}
    """
    scopes_str = os.environ.get("TARGET_SCOPES", "")
    result: dict[str, set[str]] = {}
    for scope in scopes_str.split():
        # Format: forge:read_resource or forge:write_resource
        scope = scope.removeprefix("forge:")
        if scope.startswith("read_"):
            resource = scope[5:]
            result.setdefault(resource, set()).add("read")
        elif scope.startswith("write_"):
            resource = scope[6:]
            result.setdefault(resource, set()).add("write")
    return result


def check_scopes(
    required: dict[str, list[str]],
) -> tuple[bool, list[str], list[str]]:
    """Check if required scopes are present.

    Args:
        required: {resource: [operations]} e.g., {"vpc": ["read", "write"]}

    Returns:
        (all_present, granted_list, missing_list)
    """
    scopes = get_scopes()
    granted = []
    missing = []
    for resource, operations in required.items():
        resource_scopes = scopes.get(resource, set())
        for op in operations:
            scope_str = f"{op}_{resource}"
            if op in resource_scopes:
                granted.append(scope_str)
            else:
                missing.append(scope_str)
    return len(missing) == 0, granted, missing


# =========================================================================
# Carbide API resource definitions
# =========================================================================

# All resources from the Carbide OpenAPI spec (bare-metal-manager-rest)
# with their supported operations. Derived from openapi/spec.yaml.
# Scope names use underscores (matching TARGET_SCOPES format).
CARBIDE_API_RESOURCES: dict[str, dict[str, list[str]]] = {
    # Core infrastructure
    "site":                     {"ops": ["create", "list", "get", "update", "delete"], "scope": "site"},
    "vpc":                      {"ops": ["create", "list", "get", "update", "delete"], "scope": "vpc"},
    "vpc-prefix":               {"ops": ["create", "list", "get", "update", "delete"], "scope": "vpc_prefix"},
    "subnet":                   {"ops": ["create", "list", "get", "update", "delete"], "scope": "subnet"},
    "network-security-group":   {"ops": ["create", "list", "get", "update", "delete"], "scope": "network_security_group"},
    "ipblock":                  {"ops": ["create", "list", "get", "update", "delete"], "scope": "ip_block"},
    "allocation":               {"ops": ["create", "list", "get", "update", "delete"], "scope": "allocation"},
    # Compute
    "instance":                 {"ops": ["create", "list", "get", "update", "delete"], "scope": "instance"},
    "instance-type":            {"ops": ["create", "list", "get", "update", "delete"], "scope": "instance_type"},
    "machine":                  {"ops": ["list", "get", "update", "delete"],           "scope": "machine"},
    "expected-machine":         {"ops": ["create", "list", "get", "update", "delete"], "scope": "expected_machine"},
    "operating-system":         {"ops": ["create", "list", "get", "update", "delete"], "scope": "operation_system"},
    # Networking / fabric
    "infiniband-partition":     {"ops": ["create", "list", "get", "update", "delete"], "scope": "infini_band_partition"},
    "nvlink-logical-partition": {"ops": ["create", "list", "get", "update", "delete"], "scope": None},
    "nvlink-interface":         {"ops": ["list"],                                      "scope": None},
    "dpu-extension-service":    {"ops": ["create", "list", "get", "update", "delete"], "scope": None},
    # Identity / access
    "sshkeygroup":              {"ops": ["create", "list", "get", "update", "delete"], "scope": "ssh_key_group"},
    "sshkey":                   {"ops": ["create", "list", "get", "update", "delete"], "scope": "ssh_key"},
    "tenant":                   {"ops": ["list", "get"],                               "scope": "tenant"},
    # Hardware topology
    "rack":                     {"ops": ["list", "get"],                               "scope": None},
    "tray":                     {"ops": ["list", "get"],                               "scope": None},
    "sku":                      {"ops": ["list", "get"],                               "scope": None},
    "machine-capability":       {"ops": ["list"],                                      "scope": None},
    # Observability
    "audit":                    {"ops": ["list", "get"],                               "scope": "audit"},
    "metadata":                 {"ops": ["list"],                                      "scope": None},
}

# Resource → env var for pre-existing resources.
# When set, the template only needs "read" (not "write") for that resource.
PREEXISTING_ENV_VARS: dict[str, str] = {
    "vpc": "CARBIDE_VPC_ID",
    "vpc_prefix": "CARBIDE_VPC_PREFIX_ID",
    "subnet": "CARBIDE_SUBNET_ID",
    "ssh_key_group": "CARBIDE_SSH_KEY_GROUP_ID",
    "operation_system": "CARBIDE_OS_ID",
    "instance_type": "CARBIDE_INSTANCE_TYPE",
    "instance": "CARBIDE_INSTANCE_ID",
}

# Minimum scopes each template requires to run (when creating all resources).
TEMPLATE_REQUIRED_SCOPES: dict[str, dict[str, list[str]]] = {
    "iam": {
        "tenant": ["read"],
        "site": ["read"],
        "ssh_key_group": ["read", "write"],
        "ssh_key": ["read", "write"],
    },
    "control-plane": {
        "tenant": ["read"],
        "site": ["read"],
        "ssh_key_group": ["read", "write"],
        "ssh_key": ["read", "write"],
        "vpc": ["read", "write"],
    },
    "network": {
        "vpc": ["read", "write"],
        "vpc_prefix": ["read", "write"],
        "subnet": ["read", "write"],
        "network_security_group": ["read", "write"],
    },
    "image-registry": {
        "operation_system": ["read", "write"],
        "instance_type": ["read"],
        "instance": ["read", "write"],
    },
    "bm": {
        "instance": ["read", "write"],
        "instance_type": ["read"],
        "operation_system": ["read"],
        "vpc": ["read"],
    },
}

# Keep backward-compatible alias
TEMPLATE_SCOPES = TEMPLATE_REQUIRED_SCOPES


def effective_scopes_for_template(template_name: str) -> dict[str, list[str]]:
    """Calculate effective required scopes accounting for pre-existing resources.

    When a CARBIDE_*_ID env var is set for a resource, write permission
    is not needed — only read. This lets users run templates in restricted
    environments where infrastructure is shared or pre-provisioned.

    Args:
        template_name: Template name (e.g., "control-plane", "network")

    Returns:
        {resource: [operations]} with write removed where pre-existing
    """
    base = TEMPLATE_REQUIRED_SCOPES.get(template_name, {})
    effective: dict[str, list[str]] = {}

    for resource, operations in base.items():
        env_var = PREEXISTING_ENV_VARS.get(resource)
        if env_var and os.environ.get(env_var):
            # Pre-existing: only need read
            effective[resource] = ["read"]
        else:
            effective[resource] = list(operations)

    return effective


def load_state(state_file: str | None = None) -> dict[str, Any]:
    """Load persisted state from a JSON file."""
    path = Path(state_file or os.environ.get("CARBIDE_STATE_FILE", DEFAULT_STATE_FILE))
    if path.exists():
        return json.loads(path.read_text())
    return {}


def save_state(state: dict[str, Any], state_file: str | None = None) -> None:
    """Save state to a JSON file for use by subsequent steps."""
    path = Path(state_file or os.environ.get("CARBIDE_STATE_FILE", DEFAULT_STATE_FILE))
    path.write_text(json.dumps(state, indent=2))
