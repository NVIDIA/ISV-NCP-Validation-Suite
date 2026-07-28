# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for break-fix / remediation validations (BFX01-BFX06)."""

from __future__ import annotations

import pytest

from isvtest.validations.remediation import (
    FailureNotificationCheck,
    GpuResetCheck,
    MaintenanceEventsCheck,
    NodeHealthAgentCheck,
    RepairHistoryCheck,
)


class TestMaintenanceEventsCheck:
    def test_passes_when_queryable(self) -> None:
        check = MaintenanceEventsCheck(
            config={
                "step_output": {
                    "success": True,
                    "events_queryable": True,
                    "events": [{"machine_id": "m-1", "status": "maintenance"}],
                }
            }
        )
        check.run()
        assert check.passed

    def test_skips_when_step_skipped(self) -> None:
        check = MaintenanceEventsCheck(
            config={
                "step_output": {
                    "success": True,
                    "skipped": True,
                    "skip_reason": "no machines",
                }
            }
        )
        with pytest.raises(pytest.skip.Exception):
            check.run()


class TestRepairHistoryCheck:
    def test_passes_when_history_queryable(self) -> None:
        check = RepairHistoryCheck(
            config={
                "step_output": {
                    "success": True,
                    "history_queryable": True,
                    "records": [{"machine_id": "m-1", "entries": [{"status": "Maintenance"}]}],
                }
            }
        )
        check.run()
        assert check.passed


class TestGpuResetCheck:
    def test_fails_when_not_completed(self) -> None:
        check = GpuResetCheck(
            config={"step_output": {"success": True, "operation": {"completed": False, "message": "timeout"}}}
        )
        check.run()
        assert not check.passed


class TestNodeHealthAgentCheck:
    def test_fails_when_agents_not_observable(self) -> None:
        check = NodeHealthAgentCheck(
            config={"step_output": {"success": True, "agents_observable": False, "agents": []}}
        )
        check.run()
        assert not check.passed


class TestNotificationChecks:
    def test_planned_notification_passes(self) -> None:
        check = FailureNotificationCheck(
            config={"step_output": {"success": True, "notification_channel_observable": True}}
        )
        check.run()
        assert check.passed
