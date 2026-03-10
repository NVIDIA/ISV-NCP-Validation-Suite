#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Create test namespaces for GPU network validation.

Creates the ncp-network-validation and ncp-network-validation-2
namespaces used by subsequent network validation tests.
All steps are idempotent -- safe to run repeatedly.

Environment:
    K8S_NAMESPACE: Primary namespace (default: ncp-network-validation)

Output schema: generic (fields: namespaces)
"""

import json
import subprocess
import sys
from typing import Any


def run_cmd(cmd: str, *args: str, **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [cmd] + list(args), capture_output=True, text=True,
        timeout=kwargs.get("timeout", 120),
    )


def main() -> int:
    namespaces = ["ncp-network-validation", "ncp-network-validation-2"]
    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "namespaces": [],
    }

    try:
        created = []
        for ns in namespaces:
            # Check if namespace already exists
            r = run_cmd("kubectl", "get", "namespace", ns, "--no-headers")
            if r.returncode == 0:
                print(f"Namespace '{ns}' already exists.", file=sys.stderr)
                created.append(ns)
                continue

            r = run_cmd("kubectl", "create", "namespace", ns)
            if r.returncode != 0:
                result["error"] = f"Failed to create namespace '{ns}': {r.stderr}"
                print(json.dumps(result, indent=2))
                return 1

            print(f"Namespace '{ns}' created.", file=sys.stderr)
            created.append(ns)

        result["namespaces"] = created
        result["success"] = True

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
