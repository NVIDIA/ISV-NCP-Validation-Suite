# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for break-fix / break-fix validations (BFX01-BFX06)."""

from __future__ import annotations

from typing import Any

import pytest

from isvtest.core.validation import BaseValidation
from isvtest.validations.breakfix import (
    BmcKernelLogCheck,
    CordonNodeCheck,
    FailureNotificationCheck,
    GpuResetCheck,
    HostReplacementCheck,
    MaintenanceEventsCheck,
    NodeHealthAgentCheck,
    PlannedMaintenanceNotificationCheck,
    RepairHistoryCheck,
    ReportNodeRepairCheck,
    RetirementNoticesCheck,
    ReturnNodeMaintenanceCheck,
    ReturnRackMaintenanceCheck,
)


def _run(check_class: type[BaseValidation], step_output: dict[str, Any]) -> BaseValidation:
    """Run a check against ``step_output`` and return it for assertion."""
    check = check_class(config={"step_output": step_output})
    check.run()
    return check


# (check class, observable flag key, record list key, one sample record)
# BFX05/BFX06 sit here too: a notification channel is held to the same evidence
# bar as the BFX02 query APIs, so the flag alone cannot pass the check.
_QUERYABLE_CASES = [
    (MaintenanceEventsCheck, "events_queryable", "events", {"machine_id": "m-1", "status": "maintenance"}),
    (
        RetirementNoticesCheck,
        "notices_queryable",
        "notices",
        {"machine_id": "m-1", "status": "scheduled", "retire_after": "2027-01-15T00:00:00Z"},
    ),
    (RepairHistoryCheck, "history_queryable", "records", {"machine_id": "m-1", "entries": [{"status": "x"}]}),
    (
        PlannedMaintenanceNotificationCheck,
        "notification_channel_observable",
        "notifications",
        {"machine_id": "m-1", "type": "planned_maintenance", "notified_at": "2026-06-24T12:00:00Z"},
    ),
    (
        FailureNotificationCheck,
        "notification_channel_observable",
        "notifications",
        {"machine_id": "m-1", "type": "node_failure", "notified_at": "2026-06-24T12:00:00Z"},
    ),
]

_NOTIFICATION_CASES = [
    (PlannedMaintenanceNotificationCheck, "Planned maintenance"),
    (FailureNotificationCheck, "Immediate failure"),
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

    def test_retirement_notice_needs_a_date_not_just_a_subject(self) -> None:
        """Without retire_after a notice says something will be retired, not when.

        Lead time is the whole value of a retirement notice, so a record that
        cannot demonstrate any is not evidence the API works.
        """
        step_output = {"success": True, "notices_queryable": True, "notices": [{"machine_id": "m-1"}]}
        with pytest.raises(pytest.skip.Exception):
            _run(RetirementNoticesCheck, step_output)

    def test_retirement_notice_accepts_a_rack_as_the_subject(self) -> None:
        """Providers retire whole racks as readily as single machines."""
        step_output = {
            "success": True,
            "notices_queryable": True,
            "notices": [{"rack_id": "r-1", "retire_after": "2027-01-15T00:00:00Z"}],
        }
        assert _run(RetirementNoticesCheck, step_output).passed

    @pytest.mark.parametrize(("check_class", "_label"), _NOTIFICATION_CASES)
    def test_notification_needs_a_timestamp(self, check_class: type[BaseValidation], _label: str) -> None:
        """A notification with no notified_at cannot evidence lead time or latency."""
        step_output = {
            "success": True,
            "notification_channel_observable": True,
            "notifications": [{"machine_id": "m-1", "type": "x"}],
        }
        with pytest.raises(pytest.skip.Exception):
            _run(check_class, step_output)

    @pytest.mark.parametrize(("check_class", "_label"), _NOTIFICATION_CASES)
    def test_notification_needs_a_subject(self, check_class: type[BaseValidation], _label: str) -> None:
        """A notification that does not say which machine is not actionable."""
        step_output = {
            "success": True,
            "notification_channel_observable": True,
            "notifications": [{"notified_at": "2026-06-24T12:00:00Z"}],
        }
        with pytest.raises(pytest.skip.Exception):
            _run(check_class, step_output)

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

    @pytest.mark.parametrize(
        ("check_class", "operation"),
        [
            (GpuResetCheck, {"completed": True}),
            (ReturnRackMaintenanceCheck, {"accepted": True}),
            (HostReplacementCheck, {"node_removed_from_pool": True}),
            (ReturnNodeMaintenanceCheck, {"accepted": True}),
        ],
    )
    def test_operation_must_identify_what_it_acted_on(
        self, check_class: type[BaseValidation], operation: dict[str, Any]
    ) -> None:
        """Success without an identifier is not a result, it is an assertion.

        The message would otherwise read "... for node unknown", which tells a
        reader nothing about whether the operation reached anything.
        """
        check = _run(check_class, {"success": True, "operation": operation})
        assert not check.passed
        assert "without identifying what it acted on" in check.message

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

    def test_node_repair_report_keys_off_the_observed_state(self) -> None:
        """An accepted report that never changed the node's state is not a pass.

        The provider returning 200 proves only that the API exists; the check has
        to see the node actually enter repair.
        """
        step_output = {"success": True, "operation": {"requested": True, "repair_state_observed": False}}
        assert not _run(ReportNodeRepairCheck, step_output).passed

    def test_node_repair_report_fails_a_node_left_in_repair(self) -> None:
        """Reporting a node is only non-destructive if the node comes back.

        A step that fails its own restore already reports ``success: False``. This
        covers the shapes that do not: a provider whose step forgot to, and
        ``--skip-restore``, which strands the node deliberately.
        """
        step_output = {
            "success": True,
            "operation": {"requested": True, "repair_state_observed": True, "restored": False, "node_id": "fm-1"},
        }
        check = _run(ReportNodeRepairCheck, step_output)
        assert not check.passed
        assert "left in a repair state" in check.message

    def test_node_repair_report_surfaces_a_failed_restore_from_the_step(self) -> None:
        """The script fails itself when restore fails, and that error reaches the reader."""
        step_output = {
            "success": False,
            "error": "Node left in Repairing: timeout; override delete failed",
            "operation": {"requested": True, "repair_state_observed": True, "restored": False},
        }
        check = _run(ReportNodeRepairCheck, step_output)
        assert not check.passed
        assert "Node left in Repairing" in check.message

    def test_node_repair_report_names_the_node_it_moved(self) -> None:
        """A clean pass names the node and carries no extra provider detail."""
        step_output = {
            "success": True,
            "operation": {"requested": True, "repair_state_observed": True, "restored": True, "node_id": "fm-1"},
        }
        check = _run(ReportNodeRepairCheck, step_output)
        assert check.passed
        assert "fm-1" in check.message

    def test_node_repair_report_surfaces_a_provider_finding_on_pass(self) -> None:
        """A cleanup that needed the fallback still passes, but must not do so silently."""
        step_output = {
            "success": True,
            "operation": {
                "requested": True,
                "repair_state_observed": True,
                "restored": True,
                "node_id": "fm-1",
                "message": "removed the override directly",
            },
        }
        check = _run(ReportNodeRepairCheck, step_output)
        assert check.passed
        assert "removed the override directly" in check.message


class TestBmcKernelLogCheck:
    """Cover the BFX03-03 log-history check."""

    def test_passes_when_every_host_reports_a_log(self) -> None:
        """A named host with logs available is the passing case."""
        step_output = {"success": True, "hosts": [{"host_id": "h-1", "kernel_log_available": True}]}
        assert _run(BmcKernelLogCheck, step_output).passed

    def test_fails_when_a_host_cannot_name_itself(self) -> None:
        """A host record with no host_id gives the tenant nothing to go and read."""
        step_output = {"success": True, "hosts": [{"kernel_log_available": True}]}
        check = _run(BmcKernelLogCheck, step_output)
        assert not check.passed
        assert "missing host_id" in check.message

    def test_fails_when_logs_are_unavailable(self) -> None:
        """Reporting a host whose logs cannot be read is a failure, not a pass."""
        step_output = {"success": True, "hosts": [{"host_id": "h-1", "kernel_log_available": False}]}
        assert not _run(BmcKernelLogCheck, step_output).passed


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

    @pytest.mark.parametrize(("check_class", "label"), _NOTIFICATION_CASES)
    def test_passes_when_a_notification_is_evidenced(self, check_class: type[BaseValidation], label: str) -> None:
        """An observable channel with a real notification passes and names the channel."""
        step_output = {
            "success": True,
            "notification_channel_observable": True,
            "notifications": [{"machine_id": "m-1", "message": "scheduled", "notified_at": "2026-06-24T12:00:00Z"}],
        }
        check = _run(check_class, step_output)
        assert check.passed
        assert label in check.message

    @pytest.mark.parametrize(("check_class", "label"), _NOTIFICATION_CASES)
    def test_observable_flag_alone_is_not_evidence(self, check_class: type[BaseValidation], label: str) -> None:
        """The flag is the provider asserting its own capability; it is not evidence."""
        with pytest.raises(pytest.skip.Exception):
            _run(check_class, {"success": True, "notification_channel_observable": True})

    @pytest.mark.parametrize(("check_class", "label"), _NOTIFICATION_CASES)
    def test_fails_when_channel_unobservable(self, check_class: type[BaseValidation], label: str) -> None:
        """A channel the provider cannot observe fails."""
        assert not _run(check_class, {"success": True, "notification_channel_observable": False}).passed
