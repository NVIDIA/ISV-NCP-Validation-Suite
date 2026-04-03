# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""SSH connection and utility helpers.

Provides shared functions for SSH-based validations:
- SSH client creation via paramiko
- Remote command execution
- SSH configuration extraction from config/inventory
- CPU range parsing utilities

These validations are platform-agnostic and work on ANY host with SSH access:
AWS, GCP, Azure, bare metal, etc.

Requires paramiko: pip install paramiko
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import paramiko

log = logging.getLogger(__name__)


def get_ssh_client(
    host: str,
    user: str,
    key_path: str,
    timeout: int = 30,
) -> paramiko.SSHClient:
    """Create SSH client connection using paramiko.

    Args:
        host: Hostname or IP address to connect to
        user: SSH username
        key_path: Path to SSH private key file
        timeout: Connection timeout in seconds

    Returns:
        Connected paramiko SSHClient instance
    """
    import paramiko

    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    ssh_client.connect(
        hostname=host,
        username=user,
        key_filename=key_path,
        timeout=timeout,
        allow_agent=False,
        look_for_keys=False,
    )
    return ssh_client


def run_ssh_command(
    ssh: paramiko.SSHClient,
    command: str,
    timeout: int = 120,
) -> tuple[int, str, str]:
    """Run command via SSH and return exit_code, stdout, stderr.

    Args:
        ssh: Connected SSH client
        command: Command to execute
        timeout: Per-command timeout in seconds (default: 120)

    Returns:
        Tuple of (exit_code, stdout, stderr)
    """
    _, stdout, stderr = ssh.exec_command(command, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    return exit_code, stdout.read().decode(), stderr.read().decode()


def get_ssh_config(config: dict[str, Any], inventory: dict[str, Any]) -> dict[str, Any]:
    """Extract SSH configuration from config and inventory.

    Supports multiple sources:
    - Direct config values (host, key_file, user)
    - Step output references (step_output.public_ip, etc.)
    - Inventory structures (ssh.*, vm.*)

    Args:
        config: Test configuration dictionary
        inventory: Inventory data dictionary

    Returns:
        Dictionary with ssh_host, ssh_user, ssh_key_path, and optional metadata
    """
    # Check step_output first (from Jinja2 references)
    step_output = config.get("step_output", {})

    # Try different inventory structures
    ssh_inv = inventory.get("ssh", {})
    vmaas_inv = inventory.get("vmaas", {})

    # Determine host (check multiple sources)
    host = (
        config.get("host")
        or config.get("ssh_host")
        or step_output.get("public_ip")
        or step_output.get("private_ip")
        or step_output.get("host")
        or ssh_inv.get("host")
        or ssh_inv.get("public_ip")
        or vmaas_inv.get("public_ip")
        or vmaas_inv.get("private_ip")
    )

    # Determine user
    user = (
        config.get("user")
        or config.get("ssh_user")
        or step_output.get("ssh_user")
        or ssh_inv.get("user")
        or vmaas_inv.get("ssh_user")
        or "ubuntu"
    )

    # Determine key path
    key_path = (
        config.get("key_file")
        or config.get("key_path")
        or config.get("ssh_key_path")
        or step_output.get("key_file")
        or step_output.get("key_path")
        or step_output.get("ssh_key_path")
        or ssh_inv.get("key_path")
        or vmaas_inv.get("ssh_key_path")
    )

    log.debug(
        "SSH config resolved: host=%s, user=%s, key=%s (sources: step_output.public_ip=%s, config.host=%s)",
        host,
        user,
        key_path,
        step_output.get("public_ip"),
        config.get("host"),
    )

    return {
        "ssh_host": host,
        "ssh_user": user,
        "ssh_key_path": key_path,
        # Optional metadata
        "gpu_count": config.get("expected_gpus") or vmaas_inv.get("gpu_count") or ssh_inv.get("gpu_count") or 0,
        "gpu_name": vmaas_inv.get("gpu_name") or ssh_inv.get("gpu_name"),
        "instance_type": vmaas_inv.get("instance_type") or ssh_inv.get("instance_type"),
        "ami_id": vmaas_inv.get("ami_id") or ssh_inv.get("ami_id"),
    }


def get_failed_subtests(results: list[dict[str, Any]]) -> list[str]:
    """Return names of failed (non-skipped) subtests.

    Args:
        results: List of subtest result dicts from BaseValidation._subtest_results

    Returns:
        List of failed subtest names
    """
    return [r["name"] for r in results if not r["passed"] and not r.get("skipped", False)]


def parse_cpu_range_count(cpu_range: str) -> int:
    """Parse a CPU range string like '0-3,5,7-9' and return total CPU count.

    Args:
        cpu_range: Comma-separated ranges (e.g., "0-3", "0-3,5,7-9")

    Returns:
        Total number of CPUs in the range
    """
    total = 0
    for part in cpu_range.split(","):
        part = part.strip()
        if "-" in part:
            bounds = part.split("-")
            try:
                total += int(bounds[1]) - int(bounds[0]) + 1
            except (ValueError, IndexError):
                pass
        elif part.isdigit():
            total += 1
    return total
