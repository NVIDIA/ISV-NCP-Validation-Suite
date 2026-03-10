#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Check NUMA topology on nodes."""

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
    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "numa_nodes": 0,
    }

    if not is_arm():
        result["success"] = True
        result["skipped"] = True
        result["info"] = "Not an ARM cluster — topology check skipped"
        print(json.dumps(result, indent=2))
        return 0

    node = subprocess.run(
        ["kubectl", "get", "nodes", "-l", "nvidia.com/gpu.present=true",
         "-o", "jsonpath={.items[0].metadata.name}"],
        capture_output=True, text=True, timeout=30,
    ).stdout.strip()

    if not node:
        # Fallback to any node
        node = subprocess.run(
            ["kubectl", "get", "nodes", "-o", "jsonpath={.items[0].metadata.name}"],
            capture_output=True, text=True, timeout=30,
        ).stdout.strip()

    # Check NUMA topology
    r = subprocess.run(
        ["oc", "debug", f"node/{node}", "--", "chroot", "/host",
         "bash", "-c", "ls -d /sys/devices/system/node/node* | wc -l"],
        capture_output=True, text=True, timeout=60,
    )
    numa_count = int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip().isdigit() else 0
    result["numa_nodes"] = numa_count

    # Get CPU count per NUMA node
    r = subprocess.run(
        ["oc", "debug", f"node/{node}", "--", "chroot", "/host",
         "lscpu"],
        capture_output=True, text=True, timeout=60,
    )
    if r.returncode == 0:
        for line in r.stdout.split("\n"):
            if "NUMA node(s):" in line:
                result["lscpu_numa"] = line.split(":")[-1].strip()
            elif "CPU(s):" in line and "NUMA" not in line and "On-line" not in line:
                result["total_cpus"] = line.split(":")[-1].strip()
            elif "Model name:" in line:
                result["cpu_model"] = line.split(":")[-1].strip()

    # Check GPU-NUMA affinity
    r = subprocess.run(
        ["oc", "debug", f"node/{node}", "--", "chroot", "/host",
         "bash", "-c", "for gpu in /sys/bus/pci/devices/*/numa_node; do echo $(dirname $gpu | xargs basename):$(cat $gpu); done 2>/dev/null | grep -v ':$' | head -10"],
        capture_output=True, text=True, timeout=60,
    )
    if r.returncode == 0 and r.stdout.strip():
        result["pci_numa_affinity"] = r.stdout.strip().split("\n")

    result["success"] = numa_count > 0

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
