#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Check Compliance Operator scan results.

Verifies the Compliance Operator is installed and checks for any
existing scan results. Does NOT trigger new scans.
"""

import json
import subprocess
import sys
from typing import Any


def main() -> int:
    result: dict[str, Any] = {
        "success": False,
        "platform": "openshift",
        "operator_installed": False,
        "scans_found": 0,
        "compliant": 0,
        "non_compliant": 0,
    }

    # Check if Compliance Operator is installed
    r = subprocess.run(
        ["kubectl", "get", "csv", "-n", "openshift-compliance", "--no-headers"],
        capture_output=True, text=True, timeout=30,
    )
    if r.returncode == 0 and "compliance-operator" in r.stdout:
        result["operator_installed"] = True
    else:
        result["success"] = True
        result["info"] = "Compliance Operator not installed — skipping scan check"
        print(json.dumps(result, indent=2))
        return 0

    # Check ComplianceSuite results
    r = subprocess.run(
        ["kubectl", "get", "compliancesuites", "-n", "openshift-compliance", "-o", "json"],
        capture_output=True, text=True, timeout=30,
    )
    if r.returncode == 0:
        data = json.loads(r.stdout)
        for suite in data.get("items", []):
            result["scans_found"] += 1
            phase = suite.get("status", {}).get("phase", "")
            if phase == "DONE":
                res = suite.get("status", {}).get("result", "")
                if res == "Compliant":
                    result["compliant"] += 1
                elif res == "NonCompliant":
                    result["non_compliant"] += 1

    # Check ComplianceCheckResult summary
    r = subprocess.run(
        ["kubectl", "get", "compliancecheckresults", "-n", "openshift-compliance",
         "--no-headers"],
        capture_output=True, text=True, timeout=30,
    )
    if r.returncode == 0 and r.stdout.strip():
        lines = r.stdout.strip().split("\n")
        result["total_check_results"] = len(lines)
        result["pass_count"] = sum(1 for l in lines if "PASS" in l)
        result["fail_count"] = sum(1 for l in lines if "FAIL" in l)

    result["success"] = True

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
