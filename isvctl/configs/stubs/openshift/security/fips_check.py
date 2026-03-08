#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Check FIPS mode status on the cluster."""

import json
import subprocess
import sys
from typing import Any


def main() -> int:
    result: dict[str, Any] = {"success": False, "platform": "openshift", "fips_enabled": False}

    # Check cluster-wide FIPS status via configmap
    r = subprocess.run(
        ["oc", "get", "configmap", "cluster-config-v1", "-n", "kube-system",
         "-o", "jsonpath={.data.install-config}"],
        capture_output=True, text=True, timeout=30,
    )
    if r.returncode == 0 and "fips: true" in r.stdout.lower():
        result["fips_enabled"] = True
        result["source"] = "install-config"
    else:
        # Fallback: check a node directly
        r = subprocess.run(
            ["kubectl", "get", "nodes", "-o", "jsonpath={.items[0].metadata.name}"],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode == 0 and r.stdout.strip():
            node = r.stdout.strip()
            r = subprocess.run(
                ["oc", "debug", f"node/{node}", "--", "chroot", "/host",
                 "cat", "/proc/sys/crypto/fips_enabled"],
                capture_output=True, text=True, timeout=60,
            )
            if r.returncode == 0 and r.stdout.strip() == "1":
                result["fips_enabled"] = True
                result["source"] = "kernel"

    # FIPS is optional — report status but don't fail if disabled
    result["success"] = True
    if not result["fips_enabled"]:
        result["info"] = "FIPS mode is not enabled (optional for non-regulated environments)"

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
