# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for break-fix / break-fix validations (BFX01-BFX06)."""

from __future__ import annotations

import pytest

from isvtest.validations.breakfix import (
    CordonNodeCheck,
    FailureNotificationCheck,
    GpuResetCheck,
    MaintenanceEventsCheck,
    NodeHealthAgentCheck,
    PlannedMaintenanceNotificationCheck,
    RepairHistoryCheck,
    RetirementNoticesCheck,
)


class TestMaintenanceEventsCheck:
    """Cover the BFX02-01 maintenance-event query check."""

    def test_passes_when_queryable(self) -> None:
        """A queryable API with at least one event passes."""
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
        """A provider step reporting a structured skip propagates as a pytest skip."""
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

    def test_skips_when_no_events(self) -> None:
        """Zero events cannot demonstrate the query API, so this must not pass."""
        check = MaintenanceEventsCheck(
            config={"step_output": {"success": True, "events_queryable": True, "events": []}}
        )
        with pytest.raises(pytest.skip.Exception):
            check.run()


class TestRepairHistoryCheck:
    """Cover the BFX02-03 repair-history query check."""

    def test_passes_when_history_queryable(self) -> None:
        """A queryable API with at least one machine record passes."""
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

    def test_skips_when_no_records(self) -> None:
        """Zero repair records cannot demonstrate the query API, so this must not pass."""
        check = RepairHistoryCheck(config={"step_output": {"success": True, "history_queryable": True, "records": []}})
        with pytest.raises(pytest.skip.Exception):
            check.run()


class TestRetirementNoticesCheck:
    """Cover the BFX02-02 retirement-notice query check."""

    def test_passes_when_notices_present(self) -> None:
        """A queryable API with at least one notice passes."""
        check = RetirementNoticesCheck(
            config={
                "step_output": {
                    "success": True,
                    "notices_queryable": True,
                    "notices": [{"machine_id": "m-1", "status": "scheduled"}],
                }
            }
        )
        check.run()
        assert check.passed

    def test_skips_when_no_notices(self) -> None:
        """Zero notices cannot demonstrate the query API, so this must not pass."""
        check = RetirementNoticesCheck(
            config={"step_output": {"success": True, "notices_queryable": True, "notices": []}}
        )
        with pytest.raises(pytest.skip.Exception):
            check.run()


class TestGpuResetCheck:
    """Cover the BFX01-01 GPU reset check."""

    def test_fails_when_not_completed(self) -> None:
        """An operation that never completed fails."""
        check = GpuResetCheck(
            config={"step_output": {"success": True, "operation": {"completed": False, "message": "timeout"}}}
        )
        check.run()
        assert not check.passed


class TestNodeHealthAgentCheck:
    """Cover the BFX04-01 GPUd/Sentinel health-agent check."""

    def test_fails_when_agents_not_observable(self) -> None:
        """A platform that cannot observe health agents fails."""
        check = NodeHealthAgentCheck(
            config={"step_output": {"success": True, "agents_observable": False, "agents": []}}
        )
        check.run()
        assert not check.passed

    def test_fails_when_no_agents_returned(self) -> None:
        """BFX04-01 needs evidence an agent is running; zero records is not that."""
        check = NodeHealthAgentCheck(config={"step_output": {"success": True, "agents_observable": True, "agents": []}})
        check.run()
        assert not check.passed


class TestCordonNodeCheck:
    """Cover the BFX01-04 cordon check."""

    def test_fails_when_existing_workloads_unreported(self) -> None:
        """A missing existing_workloads_running is not proof that workloads continued."""
        check = CordonNodeCheck(
            config={
                "step_output": {
                    "success": True,
                    "operation": {"cordoned": True, "new_workloads_blocked": True},
                }
            }
        )
        check.run()
        assert not check.passed


class TestNotificationChecks:
    """Cover the BFX05-01 planned and BFX06-01 immediate notification checks."""

    def test_planned_notification_passes(self) -> None:
        """An observable planned-maintenance channel passes."""
        check = PlannedMaintenanceNotificationCheck(
            config={"step_output": {"success": True, "notification_channel_observable": True}}
        )
        check.run()
        assert check.passed

    def test_failure_notification_passes(self) -> None:
        """An observable immediate-failure channel passes."""
        check = FailureNotificationCheck(
            config={"step_output": {"success": True, "notification_channel_observable": True}}
        )
        check.run()
        assert check.passed
