# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Tests for security validation classes."""

from __future__ import annotations

from typing import Any

from isvtest.validations.security import (
    BmcManagementNetworkCheck,
    MfaEnforcedCheck,
    OidcUserAuthCheck,
)

OIDC_REQUIRED_TESTS = {
    "valid_token_accepted": {"passed": True},
    "bad_signature_rejected": {"passed": True},
    "wrong_issuer_rejected": {"passed": True},
    "wrong_audience_rejected": {"passed": True},
    "expired_token_rejected": {"passed": True},
    "missing_required_claim_rejected": {"passed": True},
    "discovery_and_jwks_reachable": {"passed": True},
}


def _bmc_management_config(tests: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Build a minimal BMC management-network validation config."""
    return {
        "step_output": {
            "success": True,
            "platform": "security",
            "test_name": "bmc_management_network",
            "management_networks_checked": 1,
            "tests": tests,
        }
    }


def _mfa_output(**overrides: Any) -> dict[str, Any]:
    """Build a minimal passing MFA enforcement step_output."""
    base: dict[str, Any] = {
        "success": True,
        "platform": "security",
        "test_name": "mfa_enforcement",
        "interfaces_checked": 4,
        "tests": {
            "root_mfa_enabled": {"passed": True, "message": "Root MFA enabled"},
            "console_users_mfa": {"passed": True, "message": "3/3 users have MFA"},
            "api_mfa_policy": {"passed": True, "message": "MFA condition found"},
            "cli_mfa_policy": {"passed": True, "message": "MFA condition found"},
        },
    }
    base.update(overrides)
    return base


class TestBmcManagementNetworkCheck:
    """Tests for SEC12-01 BMC management-network validation."""

    def test_all_required_tests_pass(self) -> None:
        """Pass when all SEC12-01 contract checks passed."""
        tests = {
            "dedicated_management_network": {"passed": True},
            "restricted_management_routes": {"passed": True},
            "tenant_network_not_management": {"passed": True},
            "management_acl_enforced": {"passed": True},
        }

        result = BmcManagementNetworkCheck(config=_bmc_management_config(tests)).execute()

        assert result["passed"] is True
        assert "BMC management network dedicated and restricted" in result["output"]

    def test_failed_acl_reports_contract_key(self) -> None:
        """Fail with the specific contract key when ACL enforcement fails."""
        tests = {
            "dedicated_management_network": {"passed": True},
            "restricted_management_routes": {"passed": True},
            "tenant_network_not_management": {"passed": True},
            "management_acl_enforced": {"passed": False, "error": "ACL allows tenant CIDR"},
        }

        result = BmcManagementNetworkCheck(config=_bmc_management_config(tests)).execute()

        assert result["passed"] is False
        assert "management_acl_enforced" in result["error"]
        assert "ACL allows tenant CIDR" in result["error"]

    def test_missing_required_key_fails(self) -> None:
        """Fail when one of the four required contract keys is absent."""
        tests = {
            "dedicated_management_network": {"passed": True},
            "restricted_management_routes": {"passed": True},
            "tenant_network_not_management": {"passed": True},
        }

        result = BmcManagementNetworkCheck(config=_bmc_management_config(tests)).execute()

        assert result["passed"] is False
        assert "management_acl_enforced" in result["error"]

    def test_missing_tests_fails(self) -> None:
        """Fail when the step output does not include contract tests."""
        result = BmcManagementNetworkCheck(config={"step_output": {}}).execute()

        assert result["passed"] is False
        assert "tests" in result["error"]


class TestMfaEnforcedCheck:
    """Tests for MfaEnforcedCheck validation."""

    def test_passes_all_mfa_checks(self) -> None:
        """Happy path: all four MFA checks pass."""
        v = MfaEnforcedCheck(config={"step_output": _mfa_output()})
        result = v.execute()
        assert result["passed"] is True
        assert "4 interfaces checked" in result["output"]

    def test_fails_when_root_mfa_disabled(self) -> None:
        """Fail when root MFA is not enabled."""
        out = _mfa_output()
        out["tests"]["root_mfa_enabled"] = {"passed": False, "error": "Root MFA off"}
        v = MfaEnforcedCheck(config={"step_output": out})
        result = v.execute()
        assert result["passed"] is False
        assert "root_mfa_enabled" in result["error"]

    def test_fails_when_console_users_lack_mfa(self) -> None:
        """Fail when console users don't have MFA."""
        out = _mfa_output()
        out["tests"]["console_users_mfa"] = {"passed": False, "error": "1/3 lack MFA"}
        v = MfaEnforcedCheck(config={"step_output": out})
        result = v.execute()
        assert result["passed"] is False
        assert "console_users_mfa" in result["error"]

    def test_fails_when_api_mfa_policy_missing(self) -> None:
        """Fail when no API MFA policy exists."""
        out = _mfa_output()
        out["tests"]["api_mfa_policy"] = {"passed": False, "error": "No MFA policy"}
        v = MfaEnforcedCheck(config={"step_output": out})
        result = v.execute()
        assert result["passed"] is False
        assert "api_mfa_policy" in result["error"]

    def test_fails_when_cli_mfa_policy_missing(self) -> None:
        """Fail when no CLI MFA policy exists."""
        out = _mfa_output()
        out["tests"]["cli_mfa_policy"] = {"passed": False, "error": "No MFA policy"}
        v = MfaEnforcedCheck(config={"step_output": out})
        result = v.execute()
        assert result["passed"] is False
        assert "cli_mfa_policy" in result["error"]

    def test_fails_when_tests_dict_empty(self) -> None:
        """Fail when tests dict is missing."""
        v = MfaEnforcedCheck(config={"step_output": {"success": False}})
        result = v.execute()
        assert result["passed"] is False
        assert "tests" in result["error"].lower()

    def test_fails_when_tests_key_missing(self) -> None:
        """Fail when a required test key is absent."""
        out = _mfa_output()
        del out["tests"]["cli_mfa_policy"]
        v = MfaEnforcedCheck(config={"step_output": out})
        result = v.execute()
        assert result["passed"] is False
        assert "cli_mfa_policy" in result["error"]

    def test_uses_interfaces_checked_in_message(self) -> None:
        """Pass output should include the interfaces_checked count."""
        out = _mfa_output(interfaces_checked=7)
        v = MfaEnforcedCheck(config={"step_output": out})
        result = v.execute()
        assert result["passed"] is True
        assert "7 interfaces checked" in result["output"]


def _oidc_step_output(**overrides: Any) -> dict[str, Any]:
    """Return a valid OIDC step output with optional overrides."""
    output: dict[str, Any] = {
        "success": True,
        "issuer_url": "https://oidc.example/realms/isv",
        "audience": "isv-validation",
        "target_url": "https://api.example/protected",
        "endpoints_tested": 1,
        "tests": OIDC_REQUIRED_TESTS,
    }
    output.update(overrides)
    return output


def test_oidc_user_auth_check_passes_with_real_endpoint_metadata() -> None:
    """OidcUserAuthCheck passes when all probes and endpoint metadata are present."""
    check = OidcUserAuthCheck(config={"step_output": _oidc_step_output()})

    result = check.execute()

    assert result["passed"] is True
    assert "https://api.example/protected" in result["output"]


def test_oidc_user_auth_check_rejects_missing_target_url() -> None:
    """OidcUserAuthCheck fails old self-contained outputs without a target URL."""
    check = OidcUserAuthCheck(config={"step_output": _oidc_step_output(target_url="")})

    result = check.execute()

    assert result["passed"] is False
    assert "target_url" in result["error"]


def test_oidc_user_auth_check_requires_endpoint_probe_count() -> None:
    """OidcUserAuthCheck fails when no platform endpoint was probed."""
    check = OidcUserAuthCheck(config={"step_output": _oidc_step_output(endpoints_tested=0)})

    result = check.execute()

    assert result["passed"] is False
    assert "did not probe any platform endpoint" in result["error"]
