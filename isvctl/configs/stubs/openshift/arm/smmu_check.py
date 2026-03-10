#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Check SMMUv3 (System MMU) is available on ARM nodes."""

import json
import subprocess
import sys
from typing import Any


def is_arm() -> bool:
    r = subprocess.run(
        ["kubectl", "get", "nodes", "-o", "jsonpath={.items[0].status.nodeInfo.architecture}"],
        capture_output=True, text=True, timeout=30,
    )
    return r.returncode == 0 and r.stdout.strip() in ("arm64", "aarch64")


def main() -> int:
    result: dict[str, Any] = {"success": False, "platform": "openshift", "smmu_detected": False}

    if not is_arm():
        result["success"] = True
        result["skipped"] = True
        result["info"] = "Not an ARM cluster — SMMU check skipped"
        print(json.dumps(result, indent=2))
        return 0

    node = subprocess.run(
        ["kubectl", "get", "nodes", "-o", "jsonpath={.items[0].metadata.name}"],
        capture_output=True, text=True, timeout=30,
    ).stdout.strip()

    r = subprocess.run(
        ["oc", "debug", f"node/{node}", "--", "chroot", "/host",
         "bash", "-c", "dmesg | grep -i smmu | head -5"],
        capture_output=True, text=True, timeout=60,
    )
    smmu_output = r.stdout.strip() if r.returncode == 0 else ""

    if "smmu" in smmu_output.lower():
        result["smmu_detected"] = True
        result["smmu_version"] = "v3" if "SMMUv3" in smmu_output else "detected"
        result["dmesg_output"] = smmu_output[:500]

    # Also check /sys for IOMMU groups
    r = subprocess.run(
        ["oc", "debug", f"node/{node}", "--", "chroot", "/host",
         "bash", "-c", "ls /sys/kernel/iommu_groups/ | wc -l"],
        capture_output=True, text=True, timeout=60,
    )
    iommu_groups = int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip().isdigit() else 0
    result["iommu_groups"] = iommu_groups

    result["success"] = result["smmu_detected"] or iommu_groups > 0

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
