# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Network validations for step outputs.

Validations for VPCs, subnets, security groups, connectivity, traffic flow,
and DDI (DNS/DHCP/IP management).
"""

from __future__ import annotations

import ipaddress
import re
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    import paramiko

from isvtest.core.ssh import (
    get_failed_subtests,
    get_ssh_client,
    get_ssh_config,
    run_ssh_command,
)
from isvtest.core.validation import BaseValidation


class NetworkProvisionedCheck(BaseValidation):
    """Validate network/VPC was provisioned.

    Config:
        step_output: The step output to check

    Step output:
        network_id: Network/VPC identifier
        cidr: Network CIDR block
        subnets: Optional list of subnets
    """

    description: ClassVar[str] = "Check network was provisioned"
    markers: ClassVar[list[str]] = ["network"]

    def run(self) -> None:
        step_output = self.config.get("step_output", {})

        network_id = step_output.get("network_id")
        if not network_id:
            self.set_failed("No 'network_id' in step output")
            return

        cidr = step_output.get("cidr", "N/A")
        subnets = step_output.get("subnets", [])
        subnet_count = len(subnets) if isinstance(subnets, list) else 0

        self.set_passed(f"Network {network_id} provisioned: CIDR={cidr}, subnets={subnet_count}")


class VpcCrudCheck(BaseValidation):
    """Validate VPC CRUD operations completed successfully.

    Config:
        step_output: The step output to check

    Step output:
        tests: dict with create_vpc, read_vpc, update_tags, update_dns, delete_vpc
        Each test has 'passed' boolean
    """

    description: ClassVar[str] = "Check VPC CRUD operations"
    markers: ClassVar[list[str]] = ["network"]

    def run(self) -> None:
        step_output = self.config.get("step_output", {})
        tests = step_output.get("tests", {})

        if not tests:
            self.set_failed("No 'tests' in step output")
            return

        required_tests = ["create_vpc", "read_vpc", "update_tags", "update_dns", "delete_vpc"]
        passed_tests = []
        failed_tests = []

        for test_name in required_tests:
            test_result = tests.get(test_name, {})
            if test_result.get("passed"):
                passed_tests.append(test_name)
            else:
                error = test_result.get("error", "unknown error")
                failed_tests.append(f"{test_name}: {error}")

        if not failed_tests:
            self.set_passed(f"All {len(passed_tests)} CRUD tests passed")
        else:
            self.set_failed(f"Failed tests: {', '.join(failed_tests)}")


class SubnetConfigCheck(BaseValidation):
    """Validate subnet configuration across availability zones.

    Config:
        step_output: The step output to check
        min_subnets: Minimum number of subnets required (default: 2)
        require_multi_az: Require subnets across multiple AZs (default: True)

    Step output:
        tests: dict with create_subnets, az_distribution, subnets_available
        subnets: list of subnet info
    """

    description: ClassVar[str] = "Check subnet configuration"
    markers: ClassVar[list[str]] = ["network"]

    def run(self) -> None:
        step_output = self.config.get("step_output", {})
        tests = step_output.get("tests", {})
        subnets = step_output.get("subnets", [])

        min_subnets = self.config.get("min_subnets", 2)
        require_multi_az = self.config.get("require_multi_az", True)

        if not tests:
            self.set_failed("No 'tests' in step output")
            return

        # Check subnet count
        if len(subnets) < min_subnets:
            self.set_failed(f"Only {len(subnets)} subnets, minimum {min_subnets} required")
            return

        # Check AZ distribution
        if require_multi_az:
            az_result = tests.get("az_distribution", {})
            az_count = az_result.get("az_count", 0)
            if az_count < 2:
                self.set_failed(f"Subnets in only {az_count} AZ(s), multi-AZ required")
                return

        # Check all tests passed
        failed_tests = []
        for test_name, test_result in tests.items():
            if not test_result.get("passed"):
                failed_tests.append(test_name)

        if failed_tests:
            self.set_failed(f"Failed tests: {', '.join(failed_tests)}")
        else:
            azs = tests.get("az_distribution", {}).get("azs", [])
            self.set_passed(f"{len(subnets)} subnets across {len(azs)} AZs")


class VpcIsolationCheck(BaseValidation):
    """Validate VPC isolation - no connectivity between separate VPCs.

    Config:
        step_output: The step output to check

    Step output:
        tests: dict with no_peering, no_cross_routes_a, no_cross_routes_b, sg_isolation_*
        vpc_a, vpc_b: VPC info
    """

    description: ClassVar[str] = "Check VPC isolation"
    markers: ClassVar[list[str]] = ["network", "security"]

    def run(self) -> None:
        step_output = self.config.get("step_output", {})
        tests = step_output.get("tests", {})

        if not tests:
            self.set_failed("No 'tests' in step output")
            return

        required_tests = ["no_peering", "no_cross_routes_a", "no_cross_routes_b"]
        failed_tests = []

        for test_name in required_tests:
            test_result = tests.get(test_name, {})
            if not test_result.get("passed"):
                error = test_result.get("error", "test not found")
                failed_tests.append(f"{test_name}: {error}")

        # Also check SG isolation tests
        for key, value in tests.items():
            if key.startswith("sg_isolation") and not value.get("passed"):
                failed_tests.append(f"{key}: {value.get('error', 'failed')}")

        if failed_tests:
            self.set_failed(f"Isolation violations: {'; '.join(failed_tests)}")
        else:
            vpc_a = step_output.get("vpc_a", {}).get("id", "?")
            vpc_b = step_output.get("vpc_b", {}).get("id", "?")
            self.set_passed(f"VPCs {vpc_a} and {vpc_b} are properly isolated")


class SecurityBlockingCheck(BaseValidation):
    """Validate security group and NACL blocking rules work correctly.

    Config:
        step_output: The step output to check

    Step output:
        tests: dict with sg_default_deny_inbound, sg_allows_specific_ssh,
               sg_denies_vpc_icmp, nacl_explicit_deny, sg_restricted_egress
    """

    description: ClassVar[str] = "Check security blocking rules"
    markers: ClassVar[list[str]] = ["network", "security"]

    def run(self) -> None:
        step_output = self.config.get("step_output", {})
        tests = step_output.get("tests", {})

        if not tests:
            self.set_failed("No 'tests' in step output")
            return

        security_tests = [
            "sg_default_deny_inbound",
            "sg_allows_specific_ssh",
            "sg_denies_vpc_icmp",
            "nacl_explicit_deny",
            "sg_restricted_egress",
        ]

        passed = 0
        failed_tests = []

        for test_name in security_tests:
            test_result = tests.get(test_name, {})
            if test_result.get("passed"):
                passed += 1
            else:
                failed_tests.append(test_name)

        if failed_tests:
            self.set_failed(f"Security tests failed: {', '.join(failed_tests)}")
        else:
            self.set_passed(f"All {passed} security blocking tests passed")


class NetworkConnectivityCheck(BaseValidation):
    """Validate network connectivity for instances.

    Config:
        step_output: The step output to check

    Step output:
        instances: list of instance info with public_ip, private_ip
        tests: optional dict with connectivity test results
    """

    description: ClassVar[str] = "Check network connectivity"
    markers: ClassVar[list[str]] = ["network"]

    def run(self) -> None:
        step_output = self.config.get("step_output", {})
        instances = step_output.get("instances", [])
        tests = step_output.get("tests", {})

        if not instances:
            self.set_failed("No 'instances' in step output")
            return

        # Check instances have IPs
        instances_with_ip = 0
        for inst in instances:
            if isinstance(inst, dict):
                if inst.get("private_ip") or inst.get("public_ip"):
                    instances_with_ip += 1

        if instances_with_ip == 0:
            self.set_failed("No instances have IP addresses assigned")
            return

        # Check connectivity tests if present
        if tests:
            failed = [k for k, v in tests.items() if not v.get("passed")]
            if failed:
                self.set_failed(f"Connectivity tests failed: {', '.join(failed)}")
                return

        self.set_passed(f"{instances_with_ip} instances with network connectivity")


class TrafficFlowCheck(BaseValidation):
    """Validate real network traffic flow (ping allowed/blocked).

    Config:
        step_output: The step output to check

    Step output:
        tests: dict with traffic_allowed, traffic_blocked, internet_icmp, internet_http
    """

    description: ClassVar[str] = "Check traffic flow"
    markers: ClassVar[list[str]] = ["network"]

    def run(self) -> None:
        step_output = self.config.get("step_output", {})
        tests = step_output.get("tests", {})

        if not tests:
            self.set_failed("No 'tests' in step output")
            return

        traffic_tests = ["traffic_allowed", "traffic_blocked", "internet_icmp", "internet_http"]
        passed = []
        failed = []

        for test_name in traffic_tests:
            test_result = tests.get(test_name, {})
            if test_result.get("passed"):
                passed.append(test_name)
            else:
                error = test_result.get("error", "not found")
                failed.append(f"{test_name}: {error}")

        if failed:
            self.set_failed(f"Traffic tests failed: {'; '.join(failed)}")
        else:
            latency = tests.get("traffic_allowed", {}).get("latency_ms", "N/A")
            self.set_passed(f"All {len(passed)} traffic tests passed (latency: {latency}ms)")


class DhcpIpManagementCheck(BaseValidation):
    """Validate DHCP/IP management on an instance via SSH.

    SSHes into an instance and verifies that:
    1. A DHCP lease is active (dhclient or systemd-networkd)
    2. The instance IP matches what the platform reports
    3. DHCP-provided options (DNS, domain) are correctly configured

    Config:
        step_output: Must include public_ip or host, key_file, ssh_user
        inventory: Optional inventory for SSH config resolution

    Step output:
        public_ip: SSH target address
        private_ip: Expected private IP (for comparison)
        key_file: Path to SSH private key
        ssh_user: SSH username
    """

    description: ClassVar[str] = "Check DHCP/IP management via SSH"
    timeout: ClassVar[int] = 60
    markers: ClassVar[list[str]] = ["network", "ssh"]

    def run(self) -> None:
        try:
            import paramiko  # noqa: F401
        except ImportError:
            self.set_failed("paramiko not installed")
            return

        ssh_cfg = get_ssh_config(self.config, self.config.get("inventory", {}))
        host = ssh_cfg["ssh_host"]
        user = ssh_cfg["ssh_user"]
        key_path = ssh_cfg["ssh_key_path"]

        if not host:
            self.set_failed("No SSH host configured")
            return
        if not key_path:
            self.set_failed("No SSH key configured")
            return

        try:
            ssh = get_ssh_client(host, user, key_path)
        except Exception as e:
            self.set_failed(f"SSH connection failed: {e}")
            return

        try:
            self._check_dhcp_lease(ssh)
            self._check_ip_matches_platform(ssh)
            self._check_dhcp_options(ssh)

            failed = get_failed_subtests(self._subtest_results)
            if failed:
                self.set_failed(f"DHCP subtests failed: {', '.join(failed)}")
            else:
                self.set_passed(f"DHCP/IP management verified on {host}")
        finally:
            ssh.close()

    def _check_dhcp_lease(self, ssh: paramiko.SSHClient) -> None:
        """Check that a DHCP client is active and a valid lease exists."""
        cmd = (
            "echo '---DHCP_PROC---' && "
            "(pgrep -a 'dhclient|dhcpcd|systemd-network' 2>/dev/null || echo 'NO_DHCP_PROCESS') && "
            "echo '---DHCP_LEASE---' && "
            "(cat /var/lib/dhcp/dhclient*.leases "
            "/run/systemd/netif/leases/* "
            "/var/lib/NetworkManager/internal-*.lease "
            "/var/lib/NetworkManager/dhclient-*.lease "
            "2>/dev/null || echo 'NO_LEASE_FILES')"
        )
        _exit_code, stdout, _ = run_ssh_command(ssh, cmd)

        proc_section = ""
        lease_section = ""
        if "---DHCP_PROC---" in stdout and "---DHCP_LEASE---" in stdout:
            parts = stdout.split("---DHCP_LEASE---")
            proc_section = parts[0].split("---DHCP_PROC---")[-1].strip()
            lease_section = parts[1].strip()

        has_process = "NO_DHCP_PROCESS" not in proc_section and proc_section != ""
        has_lease = "NO_LEASE_FILES" not in lease_section and lease_section != ""

        if has_process or has_lease:
            details = []
            if has_process:
                details.append("DHCP process running")
            if has_lease:
                details.append("lease file found")
            self.report_subtest("dhcp_lease_active", True, "; ".join(details))
        else:
            self.report_subtest("dhcp_lease_active", False, "No DHCP process or lease files found")

    def _check_ip_matches_platform(self, ssh: paramiko.SSHClient) -> None:
        """Compare instance IP against platform-reported private_ip."""
        expected_ip = self.config.get("step_output", {}).get("private_ip")
        if not expected_ip:
            self.report_subtest(
                "ip_matches_platform",
                True,
                "Skipped: no private_ip in step_output",
                skipped=True,
            )
            return

        cmd = "ip -4 addr show scope global | awk '/inet / {split($2, a, \"/\"); print a[1]}'"
        _exit_code, stdout, _ = run_ssh_command(ssh, cmd)
        actual_ips = [ip.strip() for ip in stdout.strip().splitlines() if ip.strip()]

        if expected_ip in actual_ips:
            self.report_subtest(
                "ip_matches_platform",
                True,
                f"Platform IP {expected_ip} found on instance",
            )
        else:
            self.report_subtest(
                "ip_matches_platform",
                False,
                f"Expected {expected_ip}, found {actual_ips}",
            )

    def _check_dhcp_options(self, ssh: paramiko.SSHClient) -> None:
        """Verify DHCP-provided DNS and domain options are configured."""
        cmd = (
            "echo '---RESOLV---' && "
            "(cat /etc/resolv.conf 2>/dev/null || echo 'NO_RESOLV_CONF') && "
            "echo '---DHCP_OPTS---' && "
            "(grep -rh 'domain-name-servers\\|domain-name\\|ntp-servers' /var/lib/dhcp/ 2>/dev/null; "
            "grep -rh 'DNS=\\|DOMAINNAME=\\|NTP=' /run/systemd/netif/leases/ 2>/dev/null; "
            "echo 'DONE')"
        )
        _exit_code, stdout, _ = run_ssh_command(ssh, cmd)

        resolv_section = ""
        if "---RESOLV---" in stdout and "---DHCP_OPTS---" in stdout:
            parts = stdout.split("---DHCP_OPTS---")
            resolv_section = parts[0].split("---RESOLV---")[-1].strip()

        nameservers = re.findall(r"nameserver\s+([\d.]+)", resolv_section)

        if nameservers:
            self.report_subtest(
                "dhcp_options_correct",
                True,
                f"DNS servers: {', '.join(nameservers)}",
            )
        else:
            self.report_subtest(
                "dhcp_options_correct",
                False,
                "No nameserver entries found in /etc/resolv.conf",
            )


class VpcIpConfigCheck(BaseValidation):
    """Validate VPC-level IP configuration is sensible.

    Checks that:
    1. DHCP options set is configured with DNS servers
    2. Subnet CIDRs are valid, non-overlapping, and within VPC range
    3. At least one subnet has auto-assign public IP enabled

    Config:
        step_output: VPC creation output with dhcp_options, subnets, cidr
        min_ips_per_subnet: Minimum IPs per subnet (default: 16)

    Step output:
        cidr: VPC CIDR block (e.g. "10.0.0.0/16")
        subnets: list of subnet dicts with cidr, auto_assign_public_ip, available_ips
        dhcp_options: dict with domain_name_servers, domain_name, etc.
    """

    description: ClassVar[str] = "Check VPC IP configuration"
    markers: ClassVar[list[str]] = ["network"]

    def run(self) -> None:
        step_output = self.config.get("step_output", {})

        if not step_output:
            self.set_failed("No step_output provided")
            return

        self._check_dhcp_options_configured(step_output)
        self._check_subnet_cidr_valid(step_output)
        self._check_auto_assign_ip(step_output)

        failed = get_failed_subtests(self._subtest_results)
        if failed:
            self.set_failed(f"VPC IP config subtests failed: {', '.join(failed)}")
        else:
            self.set_passed("VPC IP configuration is valid")

    def _check_dhcp_options_configured(self, step_output: dict) -> None:
        """Verify DHCP options set is configured with DNS."""
        dhcp_options = step_output.get("dhcp_options")
        if not dhcp_options:
            self.report_subtest(
                "dhcp_options_configured",
                False,
                "No 'dhcp_options' in step output",
            )
            return

        dns_servers = dhcp_options.get("domain_name_servers", [])
        if not dns_servers:
            self.report_subtest(
                "dhcp_options_configured",
                False,
                "No domain_name_servers in DHCP options",
            )
            return

        domain = dhcp_options.get("domain_name", "N/A")
        self.report_subtest(
            "dhcp_options_configured",
            True,
            f"DNS: {dns_servers}, domain: {domain}",
        )

    def _check_subnet_cidr_valid(self, step_output: dict) -> None:
        """Validate subnet CIDRs are within VPC range and non-overlapping."""
        vpc_cidr_str = step_output.get("cidr")
        subnets = step_output.get("subnets", [])

        if not vpc_cidr_str:
            self.report_subtest(
                "subnet_cidr_valid",
                False,
                "No 'cidr' in step output",
            )
            return

        if not subnets:
            self.report_subtest(
                "subnet_cidr_valid",
                False,
                "No 'subnets' in step output",
            )
            return

        try:
            vpc_net = ipaddress.ip_network(vpc_cidr_str, strict=False)
        except ValueError as e:
            self.report_subtest(
                "subnet_cidr_valid",
                False,
                f"Invalid VPC CIDR: {e}",
            )
            return

        min_ips = self.config.get("min_ips_per_subnet", 16)
        subnet_nets: list[ipaddress.IPv4Network] = []
        errors: list[str] = []

        for sub in subnets:
            cidr_str = sub.get("cidr", "")
            try:
                subnet_net = ipaddress.ip_network(cidr_str, strict=False)
            except ValueError:
                errors.append(f"Invalid subnet CIDR: {cidr_str}")
                continue

            # Check within VPC range
            if not subnet_net.subnet_of(vpc_net):
                errors.append(f"{cidr_str} not within VPC {vpc_cidr_str}")

            # Check overlap with previously seen subnets
            for existing in subnet_nets:
                if subnet_net.overlaps(existing):
                    errors.append(f"{cidr_str} overlaps {existing}")

            # Check IP capacity
            available = sub.get("available_ips", subnet_net.num_addresses - 5)
            if available < min_ips:
                errors.append(f"{cidr_str} has only {available} IPs (min: {min_ips})")

            subnet_nets.append(subnet_net)

        if errors:
            self.report_subtest(
                "subnet_cidr_valid",
                False,
                "; ".join(errors),
            )
        else:
            self.report_subtest(
                "subnet_cidr_valid",
                True,
                f"{len(subnet_nets)} subnets valid within {vpc_cidr_str}",
            )

    def _check_auto_assign_ip(self, step_output: dict) -> None:
        """Check that at least one subnet has auto-assign public IP enabled."""
        subnets = step_output.get("subnets", [])

        if not subnets:
            self.report_subtest(
                "auto_assign_ip_enabled",
                False,
                "No subnets in step output",
            )
            return

        auto_assign_subnets = [
            s.get("subnet_id", s.get("cidr", "unknown")) for s in subnets if s.get("auto_assign_public_ip")
        ]

        if auto_assign_subnets:
            self.report_subtest(
                "auto_assign_ip_enabled",
                True,
                f"{len(auto_assign_subnets)} subnet(s) with auto-assign IP",
            )
        else:
            self.report_subtest(
                "auto_assign_ip_enabled",
                False,
                "No subnets have auto_assign_public_ip enabled",
            )
