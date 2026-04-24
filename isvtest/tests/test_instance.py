# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Tests for instance/VM validations."""

from __future__ import annotations

from typing import Any

from isvtest.validations.instance import InstanceRebootCheck


def _reboot_output(**overrides: Any) -> dict[str, Any]:
    """Build a minimal passing reboot step_output; overrides replace keys."""
    base: dict[str, Any] = {
        "instance_id": "i-abc123",
        "reboot_initiated": True,
        "state": "running",
        "ssh_ready": True,
        "uptime_seconds": 45.2,
        "reboot_confirmed": True,
    }
    base.update(overrides)
    return base


class TestInstanceRebootCheck:
    """Tests for InstanceRebootCheck - the check must require an affirmative
    ``reboot_confirmed: True`` rather than treating absence as success."""

    def test_passes_with_affirmative_confirmation(self) -> None:
        """Happy path: reboot_confirmed=True passes."""
        v = InstanceRebootCheck(config={"step_output": _reboot_output()})
        result = v.execute()
        assert result["passed"] is True

    def test_fails_when_reboot_confirmed_absent(self) -> None:
        """Absent key must FAIL (was silently passing)."""
        out = _reboot_output()
        del out["reboot_confirmed"]
        v = InstanceRebootCheck(config={"step_output": out})
        result = v.execute()
        assert result["passed"] is False
        assert "not affirmatively confirmed" in result["error"]

    def test_fails_when_reboot_confirmed_none(self) -> None:
        """Explicit None must FAIL - same semantic as absent."""
        v = InstanceRebootCheck(config={"step_output": _reboot_output(reboot_confirmed=None)})
        result = v.execute()
        assert result["passed"] is False
        assert "not affirmatively confirmed" in result["error"]

    def test_fails_when_reboot_confirmed_false(self) -> None:
        """Existing behavior preserved: explicit False still fails."""
        v = InstanceRebootCheck(config={"step_output": _reboot_output(reboot_confirmed=False)})
        result = v.execute()
        assert result["passed"] is False

    def test_fails_when_reboot_initiated_false(self) -> None:
        """Upstream failure mode: reboot API call never succeeded."""
        v = InstanceRebootCheck(config={"step_output": _reboot_output(reboot_initiated=False)})
        result = v.execute()
        assert result["passed"] is False
        assert "Reboot was not initiated" in result["error"]

    def test_fails_when_state_not_running(self) -> None:
        """Instance must be running after reboot."""
        v = InstanceRebootCheck(config={"step_output": _reboot_output(state="stopped")})
        result = v.execute()
        assert result["passed"] is False
        assert "not running" in result["error"]

    def test_fails_when_ssh_not_ready(self) -> None:
        """SSH connectivity must be restored post-reboot."""
        v = InstanceRebootCheck(config={"step_output": _reboot_output(ssh_ready=False)})
        result = v.execute()
        assert result["passed"] is False
        assert "SSH not ready" in result["error"]

    def test_fails_when_uptime_exceeds_max(self) -> None:
        """Uptime > max_uptime means the instance wasn't really rebooted."""
        v = InstanceRebootCheck(config={"step_output": _reboot_output(uptime_seconds=3600), "max_uptime": 600})
        result = v.execute()
        assert result["passed"] is False
        assert "reboot may not have occurred" in result["error"]
