#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Check ComputeDomain CRD exists."""

import json
import subprocess
import sys
from typing import Any


def main() -> int:
    result: dict[str, Any] = {"success": False, "platform": "openshift", "crd_exists": False}

    r = subprocess.run(
        ["kubectl", "get", "crd", "computedomains.nvidia.com", "--no-headers"],
        capture_output=True, text=True, timeout=30,
    )
    result["crd_exists"] = r.returncode == 0

    if not result["crd_exists"]:
        result["error"] = "ComputeDomain CRD not found — requires GPU Operator in DRA mode"

    result["success"] = result["crd_exists"]

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
