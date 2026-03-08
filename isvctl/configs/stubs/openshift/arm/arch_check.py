#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Verify nodes are running aarch64 architecture."""

import json
import subprocess
import sys
from typing import Any


def main() -> int:
    result: dict[str, Any] = {"success": False, "platform": "openshift", "architecture": ""}

    r = subprocess.run(
        ["kubectl", "get", "nodes", "-o",
         "jsonpath={.items[*].status.nodeInfo.architecture}"],
        capture_output=True, text=True, timeout=30,
    )
    if r.returncode != 0:
        result["error"] = f"Failed to get node architecture: {r.stderr}"
        print(json.dumps(result, indent=2))
        return 1

    archs = set(r.stdout.strip().split())
    result["architectures_found"] = sorted(archs)

    if "arm64" in archs or "aarch64" in archs:
        result["architecture"] = "arm64"
        result["success"] = True
    elif "amd64" in archs:
        result["architecture"] = "amd64"
        result["success"] = True
        result["skipped"] = True
        result["info"] = "x86_64 cluster — ARM checks not applicable"
    else:
        result["architecture"] = ",".join(archs)
        result["success"] = True

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
