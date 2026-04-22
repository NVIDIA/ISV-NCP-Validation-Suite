# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Security validations for infrastructure hardening.

Validations for BMC isolation, API endpoint exposure, tenant isolation,
and other platform security requirements (SEC* test IDs).
"""

from typing import ClassVar

from isvtest.core.validation import BaseValidation


class BmcTenantIsolationCheck(BaseValidation):
    """Validate BMC interfaces are not reachable from tenant networks.

    Verifies that management interfaces (BMC/IPMI/Redfish) are isolated
    from tenant-accessible networks — probes from the tenant network to
    known BMC endpoints must be refused or time out.

    Config:
        step_output: The step output to check

    Step output:
        tests: dict with probe_bmc_from_tenant, probe_ipmi_port,
               probe_redfish_port, reverse_path_check
    """

    description: ClassVar[str] = "Check BMC not reachable from tenant network"
    markers: ClassVar[list[str]] = ["security", "network"]

    def run(self) -> None:
        step_output = self.config.get("step_output", {})
        tests = step_output.get("tests", {})

        if not tests:
            self.set_failed("No 'tests' in step output")
            return

        required = [
            "probe_bmc_from_tenant",
            "probe_ipmi_port",
            "probe_redfish_port",
            "reverse_path_check",
        ]
        failed = []

        for test_name in required:
            test_result = tests.get(test_name, {})
            if not test_result.get("passed"):
                error = test_result.get("error", "test not found")
                failed.append(f"{test_name}: {error}")

        if failed:
            self.set_failed(f"BMC isolation tests failed: {'; '.join(failed)}")
        else:
            bmc_count = step_output.get("bmc_endpoints_tested", "N/A")
            self.set_passed(
                f"BMC interfaces unreachable from tenant network ({bmc_count} endpoints tested)"
            )


class ApiEndpointIsolationCheck(BaseValidation):
    """Validate no public internet access to API endpoints by default.

    Verifies that platform API endpoints (control plane, management APIs)
    are not directly accessible from the public internet — connections
    from outside the private network must be refused.

    Config:
        step_output: The step output to check

    Step output:
        tests: dict with probe_api_from_public, probe_mgmt_from_public,
               verify_private_only, dns_not_public
    """

    description: ClassVar[str] = "Check API endpoints not publicly accessible"
    markers: ClassVar[list[str]] = ["security", "network"]

    def run(self) -> None:
        step_output = self.config.get("step_output", {})
        tests = step_output.get("tests", {})

        if not tests:
            self.set_failed("No 'tests' in step output")
            return

        required = [
            "probe_api_from_public",
            "probe_mgmt_from_public",
            "verify_private_only",
            "dns_not_public",
        ]
        failed = []

        for test_name in required:
            test_result = tests.get(test_name, {})
            if not test_result.get("passed"):
                error = test_result.get("error", "test not found")
                failed.append(f"{test_name}: {error}")

        if failed:
            self.set_failed(f"API endpoint isolation tests failed: {'; '.join(failed)}")
        else:
            endpoints = step_output.get("endpoints_tested", "N/A")
            self.set_passed(
                f"API endpoints not publicly accessible ({endpoints} endpoints tested)"
            )
