#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Clean up ComputeDomain test resources."""

import json
import os
import subprocess
import sys
from typing import Any

NAMESPACE = os.environ.get("CD_NAMESPACE", "ncp-computedomain-validation")
DOMAIN_NAME = "ncp-test-domain"


def run_kubectl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["kubectl"] + list(args), capture_output=True, text=True, timeout=120)


def main() -> int:
    result: dict[str, Any] = {"success": True, "platform": "openshift", "resources_deleted": []}

    run_kubectl("delete", "computedomain", DOMAIN_NAME, "-n", NAMESPACE, "--ignore-not-found")
    result["resources_deleted"].append(f"computedomain/{DOMAIN_NAME}")

    run_kubectl("delete", "namespace", NAMESPACE, "--ignore-not-found")
    result["resources_deleted"].append(f"namespace/{NAMESPACE}")

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
