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

from isvtest.validations.security import BmcManagementNetworkCheck


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
