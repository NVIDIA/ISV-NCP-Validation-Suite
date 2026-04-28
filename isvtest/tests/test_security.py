# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Tests for security validations."""

from __future__ import annotations

from typing import Any

from isvtest.validations.security import BmcProtocolSecurityCheck

REQUIRED_BMC_PROTOCOL_TESTS = [
    "ipmi_disabled",
    "redfish_tls_enabled",
    "redfish_plain_http_disabled",
    "redfish_authentication_required",
    "redfish_authorization_enforced",
    "redfish_accounting_enabled",
]


def _bmc_protocol_config(
    tests: dict[str, dict[str, Any]] | None = None,
    *,
    bmc_endpoints_tested: int = 1,
) -> dict[str, Any]:
    """Build a BMC protocol validation config."""
    return {
        "step_output": {
            "bmc_endpoints_tested": bmc_endpoints_tested,
            "tests": tests
            or {name: {"passed": True, "message": f"{name} passed"} for name in REQUIRED_BMC_PROTOCOL_TESTS},
        },
    }


def test_bmc_protocol_security_check_passes_with_required_tests() -> None:
    """BmcProtocolSecurityCheck passes when every required probe passed."""
    validation = BmcProtocolSecurityCheck(config=_bmc_protocol_config())

    result = validation.execute()

    assert result["passed"] is True
    assert "BMC protocol security posture verified (1 endpoints tested)" in result["output"]


def test_bmc_protocol_security_check_reports_failed_and_missing_tests() -> None:
    """BmcProtocolSecurityCheck reports both failed and missing probes."""
    tests = {
        name: {"passed": True}
        for name in REQUIRED_BMC_PROTOCOL_TESTS
        if name not in {"redfish_tls_enabled", "redfish_accounting_enabled"}
    }
    tests["redfish_tls_enabled"] = {"passed": False, "error": "certificate expired"}
    validation = BmcProtocolSecurityCheck(config=_bmc_protocol_config(tests))

    result = validation.execute()

    assert result["passed"] is False
    assert "BMC protocol security tests failed" in result["error"]
    assert "redfish_tls_enabled: certificate expired" in result["error"]
    assert "redfish_accounting_enabled: test not found" in result["error"]
