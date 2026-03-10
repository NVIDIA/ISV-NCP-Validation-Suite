#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Validate Carbide API token and extract scopes.

Maps the IAM template's "create_user" step. Instead of creating a user
(Carbide users are managed via NGC/Keycloak), this validates the current
API token, extracts granted scopes, and creates a temporary SSH key to
prove write access works.

Usage:
    python create_user.py

Output JSON:
{
    "success": true,
    "platform": "iam",
    "username": "<tenant-name>",
    "user_id": "<tenant-id>",
    "access_key_id": "<temp-ssh-key-id>",
    "scopes": {"vpc": ["read", "write"], ...},
    "scope_count": 32
}
"""

import json
import os
import sys
import time
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common.carbide import get_scopes, load_state, run_carbide, save_state, timed_call


def main() -> int:
    result: dict[str, Any] = {
        "success": False,
        "platform": "iam",
    }

    try:
        # Validate token by calling tenant get
        tenant_data, latency = timed_call("tenant", "get")
        tenant_name = tenant_data.get("name", "")
        tenant_id = tenant_data.get("id", "")

        result["username"] = tenant_name
        result["user_id"] = tenant_id
        result["auth_latency_ms"] = round(latency * 1000)

        # Extract scopes
        scopes = get_scopes()
        result["scopes"] = {k: sorted(v) for k, v in scopes.items()}
        result["scope_count"] = sum(len(v) for v in scopes.values())

        # Prove write access: create a temporary SSH key group + key
        suffix = int(time.time())
        group_name = f"ncp-iam-test-{suffix}"

        state = load_state()

        group_resp = run_carbide("ssh-key-group", "create", "--name", group_name)
        group_id = group_resp.get("id", "")
        state["iam_ssh_key_group_id"] = group_id
        state["iam_ssh_key_group_created"] = True

        key_resp = run_carbide(
            "ssh-key", "create",
            "--name", f"ncp-iam-key-{suffix}",
            "--ssh-key-group-id", group_id,
        )
        key_id = key_resp.get("id", "")
        state["iam_ssh_key_id"] = key_id

        result["access_key_id"] = key_id
        result["success"] = True

        save_state(state)

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
