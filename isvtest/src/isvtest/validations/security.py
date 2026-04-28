# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Security validations for infrastructure hardening.

Validations for BMC isolation, BMC protocol posture, API endpoint exposure,
MFA enforcement, tenant isolation, console RBAC, and other platform security
requirements (SEC* test IDs).
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


class BmcProtocolSecurityCheck(BaseValidation):
    """Validate BMC management protocols enforce CNP10-01 controls.

    Verifies the management protocol posture for BMC endpoints:
    IPMI must be disabled, Redfish must require TLS and authentication,
    role authorization must be enforced, and AAA/accounting evidence must
    be present.

    Config:
        step_output: The step output to check

    Step output:
        tests: dict with ipmi_disabled, redfish_tls_enabled,
               redfish_plain_http_disabled, redfish_authentication_required,
               redfish_authorization_enforced, redfish_accounting_enabled
    """

    description: ClassVar[str] = "Check BMC protocol security posture"
    markers: ClassVar[list[str]] = ["security", "network"]

    def run(self) -> None:
        """Validate required BMC protocol security probe results."""
        required = [
            "ipmi_disabled",
            "redfish_tls_enabled",
            "redfish_plain_http_disabled",
            "redfish_authentication_required",
            "redfish_authorization_enforced",
            "redfish_accounting_enabled",
        ]
        if not check_required_tests(self, required, "BMC protocol security tests failed"):
            return
        bmc_count = self.config.get("step_output", {}).get("bmc_endpoints_tested", "N/A")
        self.set_passed(f"BMC protocol security posture verified ({bmc_count} endpoints tested)")


class MfaEnforcedCheck(BaseValidation):
    """Validate all administrative interfaces are protected by MFA.

    Verifies that the platform enforces Multi-Factor Authentication on
    UI (console), CLI, and API administrative access -- covering root/admin
    accounts, interactive console users, and programmatic access policies.

    Config:
        step_output: The step output to check

    Step output:
        tests: dict with root_mfa_enabled, console_users_mfa,
               api_mfa_policy, cli_mfa_policy
    """

    description: ClassVar[str] = "Check admin interfaces protected by MFA"
    markers: ClassVar[list[str]] = ["security", "iam"]

    def run(self) -> None:
        """Validate required MFA enforcement results from step output."""
        required = [
            "root_mfa_enabled",
            "console_users_mfa",
            "api_mfa_policy",
            "cli_mfa_policy",
        ]
        if not check_required_tests(self, required, "MFA enforcement tests failed"):
            return
        interfaces = self.config.get("step_output", {}).get("interfaces_checked", "N/A")
        self.set_passed(f"Admin interfaces protected by MFA ({interfaces} interfaces checked)")


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


class ConsoleRbacCheck(BaseValidation):
    """Validate interactive console access is restricted by RBAC.

    Config:
        step_output: The console_rbac step output to check

    Step output:
        instance_id: VM identifier
        access_restricted: True when unauthorized console access is denied
        restricted_actions: Non-empty list of console access permissions
        tests: dict with denied_principal_cannot_access_console,
               allowed_principal_can_access_console,
               allowed_principal_is_resource_scoped
    """

    description: ClassVar[str] = "Check console access is restricted by RBAC"
    markers: ClassVar[list[str]] = ["vm", "security", "iam"]

    def run(self) -> None:
        """Validate console RBAC provider proof from step output."""
        step_output = self.config.get("step_output", {})

        instance_id = step_output.get("instance_id")
        if not instance_id:
            self.set_failed("No 'instance_id' in step output")
            return

        access_restricted = step_output.get("access_restricted")
        if access_restricted is not True:
            self.set_failed(
                f"Console access for {instance_id} is not affirmatively restricted "
                f"(access_restricted={access_restricted!r})"
            )
            return

        restricted_actions = step_output.get("restricted_actions")
        if not isinstance(restricted_actions, list) or not restricted_actions:
            self.set_failed(f"No restricted console actions reported for {instance_id}")
            return

        required = [
            "denied_principal_cannot_access_console",
            "allowed_principal_can_access_console",
            "allowed_principal_is_resource_scoped",
        ]
        if not check_required_tests(self, required, "Console RBAC tests failed"):
            return

        rbac_model = step_output.get("rbac_model", "unknown")
        self.set_passed(
            f"Console RBAC restricted for {instance_id} "
            f"(model={rbac_model}, actions={', '.join(str(action) for action in restricted_actions)})"
        )


class OidcUserAuthCheck(BaseValidation):
    """Validate user authentication via OIDC for platform services.

    Verifies that a configured platform endpoint accepts a properly issued
    token and rejects tokens with bad signature, wrong issuer, wrong
    audience, expired exp, or missing required claims, and that the
    issuer's discovery + JWKS endpoints serve the expected metadata.

    Config:
        step_output: The step output to check

    Step output:
        issuer_url: Non-empty OIDC issuer URL
        audience: Non-empty expected audience
        target_url: Non-empty platform endpoint probed with bearer tokens
        endpoints_tested: Positive integer
        tests: dict with valid_token_accepted, bad_signature_rejected,
               wrong_issuer_rejected, wrong_audience_rejected,
               expired_token_rejected, missing_required_claim_rejected,
               discovery_and_jwks_reachable
    """

    description: ClassVar[str] = (
        "Check user auth via OIDC validates signature, issuer, audience, expiration, and required claims"
    )
    markers: ClassVar[list[str]] = ["security", "iam"]

    def run(self) -> None:
        """Validate required OIDC token verification probe results from step output."""
        required = [
            "valid_token_accepted",
            "bad_signature_rejected",
            "wrong_issuer_rejected",
            "wrong_audience_rejected",
            "expired_token_rejected",
            "missing_required_claim_rejected",
            "discovery_and_jwks_reachable",
        ]
        if not check_required_tests(self, required, "OIDC user auth tests failed"):
            return

        step_output = self.config.get("step_output", {})
        for field in ("issuer_url", "audience", "target_url"):
            value = step_output.get(field)
            if not isinstance(value, str) or not value.strip():
                self.set_failed(f"OIDC user auth output missing non-empty '{field}'")
                return

        endpoints_tested = step_output.get("endpoints_tested")
        if type(endpoints_tested) is not int or endpoints_tested < 1:
            self.set_failed("OIDC user auth did not probe any platform endpoint")
            return

        issuer = step_output["issuer_url"]
        target_url = step_output["target_url"]
        self.set_passed(f"OIDC user auth verified (issuer={issuer}, target={target_url})")
