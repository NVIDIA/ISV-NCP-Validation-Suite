# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Network validations for step outputs.

Validations for VPCs, subnets, security groups, connectivity, and traffic flow.
"""

from typing import ClassVar

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
