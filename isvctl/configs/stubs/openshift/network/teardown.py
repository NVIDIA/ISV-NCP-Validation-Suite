#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Delete test namespaces and remaining network validation resources.

Removes ncp-network-validation and ncp-network-validation-2
namespaces along with all resources they contain.

Output schema: teardown
"""

import json
import subprocess
import sys
import time
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
        "resources_deleted": [],
    }

    try:
        for ns in namespaces:
            # Check if namespace exists
            r = run_cmd("kubectl", "get", "namespace", ns, "--no-headers")
            if r.returncode != 0:
                print(f"Namespace '{ns}' does not exist, skipping.",
                      file=sys.stderr)
                continue

            # Delete all pods first (in case any are stuck)
            r = run_cmd("kubectl", "delete", "pods", "--all", "-n", ns,
                        "--grace-period=0", "--force", "--ignore-not-found")
            if r.returncode == 0:
                print(f"Deleted pods in namespace '{ns}'.", file=sys.stderr)

            # Delete all jobs
            run_cmd("kubectl", "delete", "jobs", "--all", "-n", ns,
                    "--ignore-not-found")

            # Delete all network policies
            run_cmd("kubectl", "delete", "networkpolicies", "--all", "-n", ns,
                    "--ignore-not-found")

            # Delete all NetworkAttachmentDefinitions
            run_cmd("kubectl", "delete", "net-attach-def", "--all", "-n", ns,
                    "--ignore-not-found")

            # Delete the namespace
            r = run_cmd("kubectl", "delete", "namespace", ns,
                        "--ignore-not-found", timeout=120)
            if r.returncode == 0:
                result["resources_deleted"].append(f"namespace/{ns}")
                print(f"Namespace '{ns}' deleted.", file=sys.stderr)
            else:
                print(
                    f"Warning: failed to delete namespace '{ns}': {r.stderr}",
                    file=sys.stderr,
                )

        # Wait briefly for namespace termination
        deadline = time.time() + 60
        while time.time() < deadline:
            all_gone = True
            for ns in namespaces:
                r = run_cmd("kubectl", "get", "namespace", ns, "--no-headers")
                if r.returncode == 0:
                    all_gone = False
                    break
            if all_gone:
                break
            time.sleep(5)

        result["success"] = True

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
