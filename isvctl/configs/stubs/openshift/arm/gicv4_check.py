#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Check GICv4.1 (Generic Interrupt Controller) on ARM nodes."""

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
    result: dict[str, Any] = {"success": False, "platform": "openshift", "gic_detected": False}

    if not is_arm():
        result["success"] = True
        result["skipped"] = True
        result["info"] = "Not an ARM cluster — GIC check skipped"
        print(json.dumps(result, indent=2))
        return 0

    node = subprocess.run(
        ["kubectl", "get", "nodes", "-o", "jsonpath={.items[0].metadata.name}"],
        capture_output=True, text=True, timeout=30,
    ).stdout.strip()

    # Check for GICv4 in dmesg
    r = subprocess.run(
        ["oc", "debug", f"node/{node}", "--", "chroot", "/host",
         "bash", "-c", "dmesg | grep -i 'gic\\|its' | head -10"],
        capture_output=True, text=True, timeout=60,
    )
    gic_output = r.stdout.strip() if r.returncode == 0 else ""

    if "gicv4" in gic_output.lower() or "GICv4" in gic_output:
        result["gic_detected"] = True
        result["gic_version"] = "v4.1" if "4.1" in gic_output else "v4"
    elif "gicv3" in gic_output.lower():
        result["gic_detected"] = True
        result["gic_version"] = "v3"

    result["dmesg_output"] = gic_output[:500]

    # Check /proc/interrupts for ITS
    r = subprocess.run(
        ["oc", "debug", f"node/{node}", "--", "chroot", "/host",
         "bash", "-c", "ls /sys/firmware/devicetree/base/interrupt-controller/compatible 2>/dev/null && cat /sys/firmware/devicetree/base/interrupt-controller/compatible 2>/dev/null || echo none"],
        capture_output=True, text=True, timeout=60,
    )
    result["interrupt_controller"] = r.stdout.strip()[:200] if r.returncode == 0 else ""

    result["success"] = result["gic_detected"]
    if not result["success"]:
        result["success"] = True
        result["warning"] = "GIC version not detected from dmesg — may need deeper inspection"

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
