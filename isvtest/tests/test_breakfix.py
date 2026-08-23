# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for break-fix / break-fix validations (BFX01-BFX06)."""

from __future__ import annotations

from typing import Any

import pytest

from isvtest.core.validation import BaseValidation
from isvtest.validations.breakfix import (
    CordonNodeCheck,
    FailureNotificationCheck,
    GpuResetCheck,
    HostReplacementCheck,
    MaintenanceEventsCheck,
    NodeHealthAgentCheck,
    PlannedMaintenanceNotificationCheck,
    RepairHistoryCheck,
    RetirementNoticesCheck,
    ReturnNodeMaintenanceCheck,
)


def _run(check_class: type[BaseValidation], step_output: dict[str, Any]) -> BaseValidation:
    """Run a check against ``step_output`` and return it for assertion."""
    check = check_class(config={"step_output": step_output})
    check.run()
    return check


# (check class, observable flag key, record list key, one sample record)
_QUERYABLE_CASES = [
    (MaintenanceEventsCheck, "events_queryable", "events", {"machine_id": "m-1", "status": "maintenance"}),
    (RetirementNoticesCheck, "notices_queryable", "notices", {"machine_id": "m-1", "status": "scheduled"}),
    (RepairHistoryCheck, "history_queryable", "records", {"machine_id": "m-1", "entries": [{"status": "x"}]}),
]

_NOTIFICATION_CASES = [
    (
        PlannedMaintenanceNotificationCheck,
        "Planned maintenance",
        {
            "machine_id": "m-1",
            "type": "planned_maintenance",
            "message": "Scheduled firmware maintenance",
            "notified_at": "2026-08-23T10:00:00Z",
            "scheduled_at": "2026-08-24T10:00:00Z",
            "channel": "webhook",
            "delivery_status": "delivered",
            "delivery_id": "delivery-1",
        },
    ),
    (
        FailureNotificationCheck,
        "Immediate failure",
        {
            "machine_id": "m-1",
            "type": "node_failure",
            "message": "Node became unreachable",
            "failed_at": "2026-08-23T10:00:00Z",
            "notified_at": "2026-08-23T10:00:30Z",
            "channel": "webhook",
            "delivery_status": "delivered",
            "delivery_id": "delivery-2",
        },
    ),
]


class TestQueryableRecordChecks:
    """Cover the BFX02 query checks that share _QueryableRecordsCheck."""

    @pytest.mark.parametrize(("check_class", "flag", "key", "record"), _QUERYABLE_CASES)
    def test_passes_when_records_present(
        self, check_class: type[BaseValidation], flag: str, key: str, record: dict[str, Any]
    ) -> None:
        """A queryable API with at least one record passes."""
        assert _run(check_class, {"success": True, flag: True, key: [record]}).passed

    @pytest.mark.parametrize(("check_class", "flag", "key", "record"), _QUERYABLE_CASES)
    def test_skips_when_no_records(
        self, check_class: type[BaseValidation], flag: str, key: str, record: dict[str, Any]
    ) -> None:
        """Zero records cannot demonstrate the query API, so this must not pass."""
        with pytest.raises(pytest.skip.Exception):
            _run(check_class, {"success": True, flag: True, key: []})

    @pytest.mark.parametrize(("check_class", "flag", "key", "record"), _QUERYABLE_CASES)
    def test_fails_when_not_queryable(
        self, check_class: type[BaseValidation], flag: str, key: str, record: dict[str, Any]
    ) -> None:
        """A provider that cannot expose the record type fails rather than skips."""
        assert not _run(check_class, {"success": True, flag: False, key: []}).passed

    def test_skips_when_step_skipped(self) -> None:
        """A provider step reporting a structured skip propagates as a pytest skip."""
        with pytest.raises(pytest.skip.Exception):
            _run(MaintenanceEventsCheck, {"success": True, "skipped": True, "skip_reason": "no machines"})

    def test_fails_when_step_failed(self) -> None:
        """A failed step surfaces its own error rather than a queryable-flag error."""
        check = _run(MaintenanceEventsCheck, {"success": False, "error": "auth expired"})
        assert not check.passed

    @pytest.mark.parametrize(("check_class", "flag", "key", "record"), _QUERYABLE_CASES)
    def test_skips_when_all_records_are_empty_shells(
        self, check_class: type[BaseValidation], flag: str, key: str, record: dict[str, Any]
    ) -> None:
        """A list of contentless records is not evidence, so it must not pass."""
        with pytest.raises(pytest.skip.Exception):
            _run(check_class, {"success": True, flag: True, key: [{}]})

    def test_repair_history_needs_entries_not_just_a_machine_record(self) -> None:
        """BFX02-03 counts a machine record only when it carries history entries."""
        step_output = {"success": True, "history_queryable": True, "records": [{"machine_id": "m-1", "entries": []}]}
        with pytest.raises(pytest.skip.Exception):
            _run(RepairHistoryCheck, step_output)

    def test_repair_history_ignores_entryless_records_in_the_count(self) -> None:
        """Records without entries are dropped from the reported count, not counted."""
        step_output = {
            "success": True,
            "history_queryable": True,
            "records": [{"machine_id": "m-1", "entries": []}, {"machine_id": "m-2", "entries": [{"status": "Error"}]}],
        }
        check = _run(RepairHistoryCheck, step_output)
        assert check.passed
        assert "1 machine record(s)" in check.message


class TestOperationChecks:
    """Cover the BFX01 mutating-operation checks that share _OperationCheck."""

    def test_fails_when_not_completed(self) -> None:
        """An operation that never completed fails with the provider's message."""
        check = _run(GpuResetCheck, {"success": True, "operation": {"completed": False, "message": "timeout"}})
        assert not check.passed

    def test_passes_when_completed(self) -> None:
        """A completed operation passes and names the target node."""
        check = _run(GpuResetCheck, {"success": True, "operation": {"completed": True, "node_id": "n-1"}})
        assert check.passed
        assert "n-1" in check.message

    def test_host_replacement_uses_its_own_flag(self) -> None:
        """BFX01-05 keys off node_removed_from_pool, not the generic completed flag."""
        step_output = {"success": True, "operation": {"completed": True, "node_removed_from_pool": False}}
        assert not _run(HostReplacementCheck, step_output).passed

    def test_node_maintenance_reports_mode(self) -> None:
        """BFX01-02 appends the maintenance mode the provider placed the node into."""
        step_output = {"success": True, "operation": {"accepted": True, "machine_id": "m-1", "maintenance_mode": "hw"}}
        check = _run(ReturnNodeMaintenanceCheck, step_output)
        assert check.passed
        assert "maintenance_mode=hw" in check.message


class TestNodeHealthAgentCheck:
    """Cover the BFX04-01 GPUd/Sentinel health-agent check."""

    def test_fails_when_agents_not_observable(self) -> None:
        """A platform that cannot observe health agents fails."""
        assert not _run(NodeHealthAgentCheck, {"success": True, "agents_observable": False, "agents": []}).passed

    def test_fails_when_no_agents_returned(self) -> None:
        """BFX04-01 needs evidence an agent is running; zero records is not that."""
        assert not _run(NodeHealthAgentCheck, {"success": True, "agents_observable": True, "agents": []}).passed


class TestCordonNodeCheck:
    """Cover the BFX01-04 cordon check."""

    def test_fails_when_existing_workloads_unreported(self) -> None:
        """A missing existing_workloads_running is not proof that workloads continued."""
        step_output = {"success": True, "operation": {"cordoned": True, "new_workloads_blocked": True}}
        assert not _run(CordonNodeCheck, step_output).passed


class TestNotificationChecks:
    """Cover the BFX05-01 planned and BFX06-01 immediate notification checks."""

    @pytest.mark.parametrize(("check_class", "label", "record"), _NOTIFICATION_CASES)
    def test_passes_when_a_notification_is_evidenced(
        self, check_class: type[BaseValidation], label: str, record: dict[str, Any]
    ) -> None:
        """An observable channel with a real notification passes and names the channel."""
        step_output = {
            "success": True,
            "notification_channel_observable": True,
            "notifications": [record],
        }
        check = _run(check_class, step_output)
        assert check.passed
        assert label in check.message

    @pytest.mark.parametrize(("check_class", "label", "record"), _NOTIFICATION_CASES)
    def test_observable_flag_alone_is_not_evidence(
        self, check_class: type[BaseValidation], label: str, record: dict[str, Any]
    ) -> None:
        """The flag is the provider asserting its own capability; it is not evidence."""
        with pytest.raises(pytest.skip.Exception):
            _run(check_class, {"success": True, "notification_channel_observable": True})

    @pytest.mark.parametrize(("check_class", "label", "record"), _NOTIFICATION_CASES)
    def test_fails_when_channel_unobservable(
        self, check_class: type[BaseValidation], label: str, record: dict[str, Any]
    ) -> None:
        """A channel the provider cannot observe fails."""
        assert not _run(check_class, {"success": True, "notification_channel_observable": False}).passed

    @pytest.mark.parametrize(("check_class", "label", "record"), _NOTIFICATION_CASES)
    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("delivery_status", "accepted"),
            ("delivery_id", ""),
            ("channel", "stdout"),
            ("notified_at", "not-a-timestamp"),
        ],
    )
    def test_skips_when_delivery_proof_is_incomplete(
        self,
        check_class: type[BaseValidation],
        label: str,
        record: dict[str, Any],
        field: str,
        value: str,
    ) -> None:
        """A synthesized record without successful delivery proof cannot pass."""
        bad_record = {**record, field: value}
        with pytest.raises(pytest.skip.Exception):
            _run(
                check_class,
                {
                    "success": True,
                    "notification_channel_observable": True,
                    "notifications": [bad_record],
                },
            )

    def test_planned_notification_requires_a_future_schedule(self) -> None:
        """Planned-maintenance evidence must identify maintenance after notification."""
        record = {**_NOTIFICATION_CASES[0][2], "scheduled_at": "2026-08-23T09:59:59Z"}
        with pytest.raises(pytest.skip.Exception):
            _run(
                PlannedMaintenanceNotificationCheck,
                {"success": True, "notification_channel_observable": True, "notifications": [record]},
            )

    def test_failure_notification_must_be_immediate(self) -> None:
        """Failure delivery more than five minutes after detection is not immediate."""
        record = {**_NOTIFICATION_CASES[1][2], "notified_at": "2026-08-23T10:05:01Z"}
        with pytest.raises(pytest.skip.Exception):
            _run(
                FailureNotificationCheck,
                {"success": True, "notification_channel_observable": True, "notifications": [record]},
            )

    def test_provider_specific_communication_channel_is_supported(self) -> None:
        """The provider-neutral contract accepts communication systems beyond built-ins."""
        record = {**_NOTIFICATION_CASES[0][2], "channel": "pagerduty"}
        assert _run(
            PlannedMaintenanceNotificationCheck,
            {"success": True, "notification_channel_observable": True, "notifications": [record]},
        ).passed
