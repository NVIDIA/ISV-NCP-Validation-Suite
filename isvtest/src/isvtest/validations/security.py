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

from isvtest.core.validation import BaseValidation, check_required_tests


class BmcManagementNetworkCheck(BaseValidation):
    """Validate BMC management is on a dedicated, restricted network.

    Verifies that out-of-band BMC/IPMI/Redfish management networks are not
    shared with tenant networks and that management routes and ACLs are
    restricted.

    Config:
        step_output: The step output to check

    Step output:
        tests: dict with dedicated_management_network,
               restricted_management_routes, tenant_network_not_management,
               management_acl_enforced
    """

    description: ClassVar[str] = "Check BMC management network is dedicated and restricted"
    markers: ClassVar[list[str]] = ["security", "network"]

    def run(self) -> None:
        """Validate required BMC management-network results from step output."""
        required = [
            "dedicated_management_network",
            "restricted_management_routes",
            "tenant_network_not_management",
            "management_acl_enforced",
        ]
        if not check_required_tests(self, required, "BMC management network tests failed"):
            return
        network_count = self.config.get("step_output", {}).get("management_networks_checked", "N/A")
        self.set_passed(f"BMC management network dedicated and restricted ({network_count} networks checked)")


class BmcTenantIsolationCheck(BaseValidation):
    """Validate BMC interfaces are not reachable from tenant networks.

    Verifies that management interfaces (BMC/IPMI/Redfish) are isolated
    from tenant-accessible networks - probes from the tenant network to
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
        """Validate required BMC isolation probe results from step output."""
        required = [
            "probe_bmc_from_tenant",
            "probe_ipmi_port",
            "probe_redfish_port",
            "reverse_path_check",
        ]
        if not check_required_tests(self, required, "BMC isolation tests failed"):
            return
        bmc_count = self.config.get("step_output", {}).get("bmc_endpoints_tested", "N/A")
        self.set_passed(f"BMC interfaces unreachable from tenant network ({bmc_count} endpoints tested)")


class ApiEndpointIsolationCheck(BaseValidation):
    """Validate no public internet access to API endpoints by default.

    Verifies that platform API endpoints (control plane, management APIs)
    are not directly accessible from the public internet - connections
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
        """Validate required API endpoint isolation probe results from step output."""
        required = [
            "probe_api_from_public",
            "probe_mgmt_from_public",
            "verify_private_only",
            "dns_not_public",
        ]
        if not check_required_tests(self, required, "API endpoint isolation tests failed"):
            return
        endpoints = self.config.get("step_output", {}).get("endpoints_tested", "N/A")
        self.set_passed(f"API endpoints not publicly accessible ({endpoints} endpoints tested)")
