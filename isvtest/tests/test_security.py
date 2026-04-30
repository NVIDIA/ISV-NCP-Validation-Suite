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

from copy import deepcopy
from typing import Any

import pytest

from isvtest.validations.security import (
    BmcBastionAccessCheck,
    BmcManagementNetworkCheck,
    BmcProtocolSecurityCheck,
    CustomerManagedKeyCheck,
    MfaEnforcedCheck,
    OidcUserAuthCheck,
)

REQUIRED_BMC_PROTOCOL_TESTS = [
    "ipmi_disabled",
    "redfish_tls_enabled",
    "redfish_plain_http_disabled",
    "redfish_authentication_required",
    "redfish_authorization_enforced",
    "redfish_accounting_enabled",
]

OIDC_REQUIRED_TESTS = {
    "valid_token_accepted": {"passed": True},
    "bad_signature_rejected": {"passed": True},
    "wrong_issuer_rejected": {"passed": True},
    "wrong_audience_rejected": {"passed": True},
    "expired_token_rejected": {"passed": True},
    "missing_required_claim_rejected": {"passed": True},
    "discovery_and_jwks_reachable": {"passed": True},
}

BYOK_REQUIRED_TESTS = {
    "customer_managed_key_available": {"passed": True},
    "key_manager_is_customer": {"passed": True},
    "encrypt_decrypt_roundtrip": {"passed": True},
    "resource_encrypted_with_customer_key": {"passed": True},
    "provider_managed_key_not_used": {"passed": True},
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


def _bmc_protocol_config(
    tests: dict[str, dict[str, Any]] | None = None,
    *,
    bmc_endpoints_tested: int = 1,
) -> dict[str, Any]:
    """Build a BMC protocol validation config."""
    default_tests = {name: {"passed": True, "message": f"{name} passed"} for name in REQUIRED_BMC_PROTOCOL_TESTS}
    return {
        "step_output": {
            "bmc_endpoints_tested": bmc_endpoints_tested,
            "tests": tests if tests is not None else default_tests,
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


def test_bmc_protocol_security_check_preserves_empty_tests_map() -> None:
    """BmcProtocolSecurityCheck fails when an explicit empty tests map is provided."""
    validation = BmcProtocolSecurityCheck(config=_bmc_protocol_config({}))

    result = validation.execute()

    assert result["passed"] is False
    assert result["error"] == "No 'tests' in step output"


def _bastion_access_config(tests: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Build a minimal BMC bastion-access validation config."""
    return {
        "step_output": {
            "success": True,
            "platform": "security",
            "test_name": "bmc_bastion_access",
            "management_networks_checked": 1,
            "tests": tests,
        }
    }


class TestBmcBastionAccessCheck:
    """Tests for SEC12-03 BMC bastion-access validation."""

    def test_all_required_tests_pass(self) -> None:
        """Pass when all SEC12-03 contract checks passed."""
        tests = {
            "bastion_identifiable": {"passed": True},
            "management_ingress_via_bastion_only": {"passed": True},
            "no_direct_public_route": {"passed": True},
            "bastion_hardened": {"passed": True},
        }

        result = BmcBastionAccessCheck(config=_bastion_access_config(tests)).execute()

        assert result["passed"] is True
        assert "BMC reachable only via hardened bastion" in result["output"]

    def test_failed_bastion_hardened_reports_contract_key(self) -> None:
        """Fail with the specific contract key when bastion hardening fails."""
        tests = {
            "bastion_identifiable": {"passed": True},
            "management_ingress_via_bastion_only": {"passed": True},
            "no_direct_public_route": {"passed": True},
            "bastion_hardened": {"passed": False, "error": "SSH open to 0.0.0.0/0"},
        }

        result = BmcBastionAccessCheck(config=_bastion_access_config(tests)).execute()

        assert result["passed"] is False
        assert "bastion_hardened" in result["error"]
        assert "0.0.0.0/0" in result["error"]

    def test_missing_required_key_fails(self) -> None:
        """Fail when one of the four required contract keys is absent."""
        tests = {
            "bastion_identifiable": {"passed": True},
            "management_ingress_via_bastion_only": {"passed": True},
            "no_direct_public_route": {"passed": True},
        }

        result = BmcBastionAccessCheck(config=_bastion_access_config(tests)).execute()

        assert result["passed"] is False
        assert "bastion_hardened" in result["error"]

    def test_missing_tests_fails(self) -> None:
        """Fail when the step output does not include contract tests."""
        result = BmcBastionAccessCheck(config={"step_output": {}}).execute()

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


def _byok_step_output(**overrides: Any) -> dict[str, Any]:
    """Return a valid BYOK step output with optional overrides."""
    output: dict[str, Any] = {
        "success": True,
        "platform": "security",
        "test_name": "customer_managed_key_test",
        "key_id": "cmk-test-123",
        "key_arn": "arn:provider:kms:region:tenant:key/cmk-test-123",
        "encrypted_resource_id": "volume-test-123",
        "encrypted_resource_kms_key_id": "cmk-test-123",
        "tests": deepcopy(BYOK_REQUIRED_TESTS),
    }
    output.update(overrides)
    return output


def test_customer_managed_key_check_passes_with_required_evidence() -> None:
    """CustomerManagedKeyCheck passes with all required BYOK checks and evidence."""
    check = CustomerManagedKeyCheck(config={"step_output": _byok_step_output()})

    result = check.execute()

    assert result["passed"] is True
    assert "Customer-managed key encryption verified" in result["output"]
    assert "cmk-test-123" in result["output"]


def test_byok_step_output_returns_independent_tests() -> None:
    """BYOK step output helper returns independent nested test data."""
    first = _byok_step_output()
    second = _byok_step_output()

    first["tests"]["customer_managed_key_available"]["passed"] = False

    assert second["tests"]["customer_managed_key_available"]["passed"] is True
    assert BYOK_REQUIRED_TESTS["customer_managed_key_available"]["passed"] is True


def test_customer_managed_key_check_fails_when_required_check_fails() -> None:
    """CustomerManagedKeyCheck fails with the specific failed BYOK probe."""
    tests = dict(BYOK_REQUIRED_TESTS)
    tests["provider_managed_key_not_used"] = {"passed": False, "error": "AWS-managed key selected"}
    check = CustomerManagedKeyCheck(config={"step_output": _byok_step_output(tests=tests)})

    result = check.execute()

    assert result["passed"] is False
    assert "provider_managed_key_not_used" in result["error"]
    assert "AWS-managed key selected" in result["error"]


def test_customer_managed_key_check_fails_when_required_check_missing() -> None:
    """CustomerManagedKeyCheck fails when a required BYOK probe is missing."""
    tests = {
        name: result for name, result in BYOK_REQUIRED_TESTS.items() if name != "resource_encrypted_with_customer_key"
    }
    check = CustomerManagedKeyCheck(config={"step_output": _byok_step_output(tests=tests)})

    result = check.execute()

    assert result["passed"] is False
    assert "resource_encrypted_with_customer_key" in result["error"]


def test_customer_managed_key_check_fails_without_key_evidence() -> None:
    """CustomerManagedKeyCheck fails when no key evidence is reported."""
    check = CustomerManagedKeyCheck(config={"step_output": _byok_step_output(key_id="", key_arn="")})

    result = check.execute()

    assert result["passed"] is False
    assert "key evidence" in result["error"]


def test_customer_managed_key_check_fails_without_resource_evidence() -> None:
    """CustomerManagedKeyCheck fails when no encrypted resource evidence is reported."""
    check = CustomerManagedKeyCheck(config={"step_output": _byok_step_output(encrypted_resource_id="", resource_id="")})

    result = check.execute()

    assert result["passed"] is False
    assert "encrypted resource evidence" in result["error"]


def test_customer_managed_key_check_falls_back_from_blank_evidence() -> None:
    """CustomerManagedKeyCheck falls back when preferred evidence fields are blank."""
    check = CustomerManagedKeyCheck(
        config={
            "step_output": _byok_step_output(
                key_id="   ",
                key_arn="  arn:provider:kms:region:tenant:key/fallback-key  ",
                encrypted_resource_id="   ",
                resource_id="  volume-fallback-123  ",
            )
        }
    )

    result = check.execute()

    assert result["passed"] is True
    assert "fallback-key" in result["output"]
    assert "volume-fallback-123" in result["output"]


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


def test_oidc_user_auth_check_skips_when_step_marks_skipped() -> None:
    """OidcUserAuthCheck pytest.skips when the step output flags itself as skipped."""
    step_output = {
        "success": True,
        "skipped": True,
        "skip_reason": "OIDC validation not configured; missing --issuer-url or OIDC_ISSUER_URL",
        "tests": {},
    }
    check = OidcUserAuthCheck(config={"step_output": step_output})

    with pytest.raises(pytest.skip.Exception, match="OIDC validation not configured"):
        check.run()
