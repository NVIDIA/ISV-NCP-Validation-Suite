# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Tests for network DDI validations (DHCP/IP management)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from isvtest.validations.network import DhcpIpManagementCheck, VpcIpConfigCheck

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_ssh_run(
    responses: dict[str, tuple[int, str, str]],
) -> Any:
    """Create a mock run_ssh_command that returns canned responses by substring match."""

    def _run(ssh: MagicMock, command: str) -> tuple[int, str, str]:
        for pattern, response in responses.items():
            if pattern in command:
                return response
        return (1, "", "unknown command")

    return _run


def _dhcp_config(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a minimal DHCP validation config with SSH details."""
    cfg: dict[str, Any] = {
        "step_output": {
            "public_ip": "3.1.2.3",
            "private_ip": "10.0.1.5",
            "key_file": "/tmp/test.pem",
            "ssh_user": "ubuntu",
        },
    }
    if extra:
        cfg.update(extra)
    return cfg


def _vpc_config(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a minimal VPC IP config validation config."""
    cfg: dict[str, Any] = {
        "step_output": {
            "network_id": "vpc-abc123",
            "cidr": "10.0.0.0/16",
            "subnets": [
                {
                    "subnet_id": "subnet-aaa",
                    "cidr": "10.0.1.0/24",
                    "az": "us-west-2a",
                    "auto_assign_public_ip": True,
                    "available_ips": 251,
                },
                {
                    "subnet_id": "subnet-bbb",
                    "cidr": "10.0.2.0/24",
                    "az": "us-west-2b",
                    "auto_assign_public_ip": False,
                    "available_ips": 251,
                },
            ],
            "dhcp_options": {
                "dhcp_options_id": "dopt-xxx",
                "domain_name": "ec2.internal",
                "domain_name_servers": ["AmazonProvidedDNS"],
                "ntp_servers": [],
            },
        },
    }
    if extra:
        cfg["step_output"].update(extra)
    return cfg


# Mock SSH command outputs
DHCP_PROC_AND_LEASE = (
    "---DHCP_PROC---\n"
    "1234 dhclient -4 -v -pf /run/dhclient.eth0.pid eth0\n"
    "---DHCP_LEASE---\n"
    "lease {\n"
    '  interface "eth0";\n'
    "  fixed-address 10.0.1.5;\n"
    "  option domain-name-servers 10.0.0.2;\n"
    '  option domain-name "ec2.internal";\n'
    "}"
)

DHCP_LEASE_ONLY = (
    "---DHCP_PROC---\n"
    "NO_DHCP_PROCESS\n"
    "---DHCP_LEASE---\n"
    "[DHCP]\n"
    "ADDRESS=10.0.1.5/24\n"
    "DNS=10.0.0.2\n"
    "DOMAINNAME=ec2.internal\n"
)

DHCP_NONE = "---DHCP_PROC---\nNO_DHCP_PROCESS\n---DHCP_LEASE---\nNO_LEASE_FILES"

IP_ADDR_MATCH = "10.0.1.5\n"

IP_ADDR_MISMATCH = "10.0.2.99\n"

RESOLV_WITH_DNS = (
    "---RESOLV---\n"
    "nameserver 10.0.0.2\n"
    "search ec2.internal\n"
    "---DHCP_OPTS---\n"
    "option domain-name-servers 10.0.0.2;\n"
    "DONE"
)

RESOLV_NO_DNS = "---RESOLV---\nNO_RESOLV_CONF\n---DHCP_OPTS---\nDONE"


# ---------------------------------------------------------------------------
# TestDhcpIpManagementCheck
# ---------------------------------------------------------------------------


class TestDhcpIpManagementCheck:
    """Tests for DhcpIpManagementCheck validation."""

    @patch("isvtest.validations.network.get_ssh_client")
    @patch("isvtest.validations.network.run_ssh_command")
    def test_all_pass(self, mock_run: MagicMock, mock_ssh: MagicMock) -> None:
        """All 3 subtests pass with valid DHCP configuration."""
        mock_ssh.return_value = MagicMock()
        mock_run.side_effect = _mock_ssh_run(
            {
                "pgrep": (0, DHCP_PROC_AND_LEASE, ""),
                "ip -4 addr": (0, IP_ADDR_MATCH, ""),
                "resolv.conf": (0, RESOLV_WITH_DNS, ""),
            }
        )

        v = DhcpIpManagementCheck(config=_dhcp_config())
        result = v.execute()
        assert result["passed"] is True
        assert "DHCP/IP management verified" in result["output"]

    @patch("isvtest.validations.network.get_ssh_client")
    @patch("isvtest.validations.network.run_ssh_command")
    def test_dhcp_lease_not_found(self, mock_run: MagicMock, mock_ssh: MagicMock) -> None:
        """Fail when no DHCP process or lease files found."""
        mock_ssh.return_value = MagicMock()
        mock_run.side_effect = _mock_ssh_run(
            {
                "pgrep": (0, DHCP_NONE, ""),
                "ip -4 addr": (0, IP_ADDR_MATCH, ""),
                "resolv.conf": (0, RESOLV_WITH_DNS, ""),
            }
        )

        v = DhcpIpManagementCheck(config=_dhcp_config())
        result = v.execute()
        assert result["passed"] is False
        assert "dhcp_lease_active" in result["error"]

    @patch("isvtest.validations.network.get_ssh_client")
    @patch("isvtest.validations.network.run_ssh_command")
    def test_dhcp_lease_only_no_process(self, mock_run: MagicMock, mock_ssh: MagicMock) -> None:
        """Pass when DHCP lease exists but no process (systemd-networkd)."""
        mock_ssh.return_value = MagicMock()
        mock_run.side_effect = _mock_ssh_run(
            {
                "pgrep": (0, DHCP_LEASE_ONLY, ""),
                "ip -4 addr": (0, IP_ADDR_MATCH, ""),
                "resolv.conf": (0, RESOLV_WITH_DNS, ""),
            }
        )

        v = DhcpIpManagementCheck(config=_dhcp_config())
        result = v.execute()
        assert result["passed"] is True

    @patch("isvtest.validations.network.get_ssh_client")
    @patch("isvtest.validations.network.run_ssh_command")
    def test_ip_mismatch(self, mock_run: MagicMock, mock_ssh: MagicMock) -> None:
        """Fail when actual IP doesn't match platform-reported IP."""
        mock_ssh.return_value = MagicMock()
        mock_run.side_effect = _mock_ssh_run(
            {
                "pgrep": (0, DHCP_PROC_AND_LEASE, ""),
                "ip -4 addr": (0, IP_ADDR_MISMATCH, ""),
                "resolv.conf": (0, RESOLV_WITH_DNS, ""),
            }
        )

        v = DhcpIpManagementCheck(config=_dhcp_config())
        result = v.execute()
        assert result["passed"] is False
        assert "ip_matches_platform" in result["error"]

    @patch("isvtest.validations.network.get_ssh_client")
    @patch("isvtest.validations.network.run_ssh_command")
    def test_ip_check_skipped_no_private_ip(self, mock_run: MagicMock, mock_ssh: MagicMock) -> None:
        """ip_matches_platform is skipped when no private_ip in step_output."""
        mock_ssh.return_value = MagicMock()
        mock_run.side_effect = _mock_ssh_run(
            {
                "pgrep": (0, DHCP_PROC_AND_LEASE, ""),
                "ip -4 addr": (0, IP_ADDR_MATCH, ""),
                "resolv.conf": (0, RESOLV_WITH_DNS, ""),
            }
        )

        cfg = _dhcp_config()
        del cfg["step_output"]["private_ip"]
        v = DhcpIpManagementCheck(config=cfg)
        result = v.execute()
        assert result["passed"] is True

    def test_missing_ssh_host(self) -> None:
        """Fail when no SSH host is configured."""
        v = DhcpIpManagementCheck(config={"step_output": {}})
        result = v.execute()
        assert result["passed"] is False
        assert "No SSH host" in result["error"]

    def test_missing_ssh_key(self) -> None:
        """Fail when SSH key path is missing."""
        cfg = _dhcp_config()
        del cfg["step_output"]["key_file"]
        v = DhcpIpManagementCheck(config=cfg)
        result = v.execute()
        assert result["passed"] is False
        assert "No SSH key" in result["error"]

    @patch("isvtest.validations.network.get_ssh_client")
    def test_ssh_connection_failure(self, mock_ssh: MagicMock) -> None:
        """Fail when SSH connection raises exception."""
        mock_ssh.side_effect = Exception("Connection refused")

        v = DhcpIpManagementCheck(config=_dhcp_config())
        result = v.execute()
        assert result["passed"] is False
        assert "SSH connection failed" in result["error"]

    @patch("isvtest.validations.network.get_ssh_client")
    @patch("isvtest.validations.network.run_ssh_command")
    def test_dns_not_configured(self, mock_run: MagicMock, mock_ssh: MagicMock) -> None:
        """Fail when resolv.conf has no nameserver entries."""
        mock_ssh.return_value = MagicMock()
        mock_run.side_effect = _mock_ssh_run(
            {
                "pgrep": (0, DHCP_PROC_AND_LEASE, ""),
                "ip -4 addr": (0, IP_ADDR_MATCH, ""),
                "resolv.conf": (0, RESOLV_NO_DNS, ""),
            }
        )

        v = DhcpIpManagementCheck(config=_dhcp_config())
        result = v.execute()
        assert result["passed"] is False
        assert "dhcp_options_correct" in result["error"]

    @patch("isvtest.validations.network.get_ssh_client")
    @patch("isvtest.validations.network.run_ssh_command")
    def test_systemd_networkd_lease(self, mock_run: MagicMock, mock_ssh: MagicMock) -> None:
        """Pass with systemd-networkd style lease format."""
        mock_ssh.return_value = MagicMock()
        mock_run.side_effect = _mock_ssh_run(
            {
                "pgrep": (0, DHCP_LEASE_ONLY, ""),
                "ip -4 addr": (0, IP_ADDR_MATCH, ""),
                "resolv.conf": (0, RESOLV_WITH_DNS, ""),
            }
        )

        v = DhcpIpManagementCheck(config=_dhcp_config())
        result = v.execute()
        assert result["passed"] is True
        # Verify subtests include lease info
        subtests = result.get("subtests", [])
        lease_subtest = next((s for s in subtests if s["name"] == "dhcp_lease_active"), None)
        assert lease_subtest is not None
        assert lease_subtest["passed"] is True
        assert "lease file found" in lease_subtest["message"]


# ---------------------------------------------------------------------------
# TestVpcIpConfigCheck
# ---------------------------------------------------------------------------


class TestVpcIpConfigCheck:
    """Tests for VpcIpConfigCheck validation."""

    def test_all_pass(self) -> None:
        """All subtests pass with valid VPC config."""
        v = VpcIpConfigCheck(config=_vpc_config())
        result = v.execute()
        assert result["passed"] is True
        assert "VPC IP configuration is valid" in result["output"]

    def test_missing_dhcp_options(self) -> None:
        """Fail when no dhcp_options in step_output."""
        cfg = _vpc_config()
        del cfg["step_output"]["dhcp_options"]
        v = VpcIpConfigCheck(config=cfg)
        result = v.execute()
        assert result["passed"] is False
        assert "dhcp_options_configured" in result["error"]

    def test_no_dns_servers(self) -> None:
        """Fail when dhcp_options has empty DNS servers."""
        cfg = _vpc_config({"dhcp_options": {"domain_name_servers": []}})
        v = VpcIpConfigCheck(config=cfg)
        result = v.execute()
        assert result["passed"] is False
        assert "dhcp_options_configured" in result["error"]

    def test_overlapping_subnet_cidrs(self) -> None:
        """Fail when subnets have overlapping CIDRs."""
        cfg = _vpc_config(
            {
                "subnets": [
                    {
                        "subnet_id": "subnet-a",
                        "cidr": "10.0.1.0/24",
                        "auto_assign_public_ip": True,
                        "available_ips": 251,
                    },
                    {
                        "subnet_id": "subnet-b",
                        "cidr": "10.0.1.0/25",
                        "auto_assign_public_ip": True,
                        "available_ips": 123,
                    },
                ],
            }
        )
        v = VpcIpConfigCheck(config=cfg)
        result = v.execute()
        assert result["passed"] is False
        assert "subnet_cidr_valid" in result["error"]

    def test_subnet_outside_vpc_cidr(self) -> None:
        """Fail when subnet is not within VPC CIDR range."""
        cfg = _vpc_config(
            {
                "subnets": [
                    {
                        "subnet_id": "subnet-a",
                        "cidr": "192.168.1.0/24",
                        "auto_assign_public_ip": True,
                        "available_ips": 251,
                    },
                ],
            }
        )
        v = VpcIpConfigCheck(config=cfg)
        result = v.execute()
        assert result["passed"] is False
        assert "subnet_cidr_valid" in result["error"]

    def test_insufficient_ips(self) -> None:
        """Fail when subnet has fewer IPs than minimum."""
        cfg = _vpc_config(
            {
                "subnets": [
                    {
                        "subnet_id": "subnet-a",
                        "cidr": "10.0.1.0/29",
                        "auto_assign_public_ip": True,
                        "available_ips": 3,
                    },
                ],
            }
        )
        v = VpcIpConfigCheck(config=cfg)
        result = v.execute()
        assert result["passed"] is False
        assert "subnet_cidr_valid" in result["error"]

    def test_no_auto_assign(self) -> None:
        """Fail when no subnet has auto-assign public IP enabled."""
        cfg = _vpc_config(
            {
                "subnets": [
                    {
                        "subnet_id": "subnet-a",
                        "cidr": "10.0.1.0/24",
                        "auto_assign_public_ip": False,
                        "available_ips": 251,
                    },
                    {
                        "subnet_id": "subnet-b",
                        "cidr": "10.0.2.0/24",
                        "auto_assign_public_ip": False,
                        "available_ips": 251,
                    },
                ],
            }
        )
        v = VpcIpConfigCheck(config=cfg)
        result = v.execute()
        assert result["passed"] is False
        assert "auto_assign_ip_enabled" in result["error"]

    def test_auto_assign_mode_instance_passes_without_subnet_flag(self) -> None:
        """GCP-style: external IPs are per-instance, no subnet flag expected."""
        cfg = _vpc_config(
            {
                "subnets": [
                    {
                        "subnet_id": "subnet-a",
                        "cidr": "10.0.1.0/24",
                        "auto_assign_public_ip": False,
                        "available_ips": 251,
                    },
                ],
            }
        )
        cfg["auto_assign_ip_mode"] = "instance"
        v = VpcIpConfigCheck(config=cfg)
        result = v.execute()
        assert result["passed"] is True

    def test_auto_assign_mode_disabled_passes(self) -> None:
        """Deployments that don't expose public IPs pass the subtest."""
        cfg = _vpc_config(
            {
                "subnets": [
                    {
                        "subnet_id": "subnet-a",
                        "cidr": "10.0.1.0/24",
                        "auto_assign_public_ip": False,
                        "available_ips": 251,
                    },
                ],
            }
        )
        cfg["auto_assign_ip_mode"] = "disabled"
        v = VpcIpConfigCheck(config=cfg)
        result = v.execute()
        assert result["passed"] is True

    def test_auto_assign_mode_invalid_fails(self) -> None:
        """Unknown mode values are a config error."""
        cfg = _vpc_config()
        cfg["auto_assign_ip_mode"] = "something-else"
        v = VpcIpConfigCheck(config=cfg)
        result = v.execute()
        assert result["passed"] is False
        assert "auto_assign_ip_enabled" in result["error"]

    def test_auto_assign_mode_subnet_is_default(self) -> None:
        """Omitting mode keeps the current AWS-compatible behavior."""
        cfg = _vpc_config(
            {
                "subnets": [
                    {
                        "subnet_id": "subnet-a",
                        "cidr": "10.0.1.0/24",
                        "auto_assign_public_ip": False,
                        "available_ips": 251,
                    },
                ],
            }
        )
        # No auto_assign_ip_mode set -> default "subnet" -> must fail since
        # no subnet has auto_assign_public_ip=True.
        v = VpcIpConfigCheck(config=cfg)
        result = v.execute()
        assert result["passed"] is False
        assert "auto_assign_ip_enabled" in result["error"]
