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
    NvSwitchFirmwareCheck,
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
        {
            "machine_id": "m-1",
            "type": "planned_maintenance",
            "notified_at": "2026-06-24T12:00:00Z",
            "window_start": "2026-07-01T02:00:00Z",
        },
    ),
    (
        FailureNotificationCheck,
        "notification_channel_observable",
        "notifications",
        {
            "machine_id": "m-1",
            "type": "node_failure",
            "detected_at": "2026-06-24T11:59:30Z",
            "notified_at": "2026-06-24T12:00:00Z",
        },
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
    def test_notification_needs_both_timestamps(self, check_class: type[BaseValidation], _label: str) -> None:
        """One timestamp cannot evidence an interval, and the interval is the contract.

        ``notified_at`` alone shows only that something arrived: BFX05-01 needs
        the window it preceded, BFX06-01 the detection it followed.
        """
        step_output = {
            "success": True,
            "notification_channel_observable": True,
            "notifications": [{"machine_id": "m-1", "type": "x", "notified_at": "2026-06-24T12:00:00Z"}],
        }
        with pytest.raises(pytest.skip.Exception):
            _run(check_class, step_output)

    @pytest.mark.parametrize(("check_class", "_label"), _NOTIFICATION_CASES)
    def test_notification_needs_a_subject(self, check_class: type[BaseValidation], _label: str) -> None:
        """A notification that does not say which machine is not actionable."""
        step_output = {
            "success": True,
            "notification_channel_observable": True,
            "notifications": [
                {
                    "detected_at": "2026-06-24T11:59:30Z",
                    "notified_at": "2026-06-24T12:00:00Z",
                    "window_start": "2026-07-01T02:00:00Z",
                }
            ],
        }
        with pytest.raises(pytest.skip.Exception):
            _run(check_class, step_output)

    def test_planned_notice_must_precede_the_window(self) -> None:
        """A warning that arrives after maintenance starts is not a warning."""
        step_output = {
            "success": True,
            "notification_channel_observable": True,
            "notifications": [
                {
                    "machine_id": "m-1",
                    "notified_at": "2026-07-01T03:00:00Z",
                    "window_start": "2026-07-01T02:00:00Z",
                }
            ],
        }
        with pytest.raises(pytest.skip.Exception):
            _run(PlannedMaintenanceNotificationCheck, step_output)

    def test_failure_notice_must_follow_detection(self) -> None:
        """Being told before the provider knew is a malformed record, not low latency."""
        step_output = {
            "success": True,
            "notification_channel_observable": True,
            "notifications": [
                {
                    "machine_id": "m-1",
                    "detected_at": "2026-06-24T12:00:00Z",
                    "notified_at": "2026-06-24T11:59:30Z",
                }
            ],
        }
        with pytest.raises(pytest.skip.Exception):
            _run(FailureNotificationCheck, step_output)

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

    def test_fails_when_not_accepted(self) -> None:
        """An operation the provider refused fails with the provider's message."""
        check = _run(GpuResetCheck, {"success": True, "operation": {"accepted": False, "message": "timeout"}})
        assert not check.passed

    def test_passes_when_accepted(self) -> None:
        """An accepted request passes and names the target node."""
        step_output = {
            "success": True,
            "operation": {"accepted": True, "node_id": "n-1", "gpu_ids": ["GPU-0"], "request_id": "req-1"},
        }
        check = _run(GpuResetCheck, step_output)
        assert check.passed
        assert "n-1" in check.message

    def test_gpu_reset_needs_a_handle_to_poll(self) -> None:
        """A reset completes asynchronously, so acceptance without a handle is a dead end."""
        step_output = {"success": True, "operation": {"accepted": True, "node_id": "n-1", "gpu_ids": ["GPU-0"]}}
        check = _run(GpuResetCheck, step_output)
        assert not check.passed
        assert "request_id" in check.message

    def test_gpu_reset_needs_to_name_the_gpus(self) -> None:
        """A node has many GPUs, so a request that names none has not been scoped."""
        step_output = {
            "success": True,
            "operation": {"accepted": True, "node_id": "n-1", "gpu_ids": [], "request_id": "req-1"},
        }
        check = _run(GpuResetCheck, step_output)
        assert not check.passed
        assert "gpu_ids" in check.message

    @pytest.mark.parametrize(
        ("check_class", "operation"),
        [
            (GpuResetCheck, {"accepted": True, "gpu_ids": ["GPU-0"], "request_id": "req-1"}),
            (ReturnRackMaintenanceCheck, {"accepted": True}),
            (HostReplacementCheck, {"node_removed_from_pool": True}),
            (ReturnNodeMaintenanceCheck, {"instance_deleted": True, "machine_quarantined": True}),
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

    def test_node_return_passes_when_relinquished_and_held(self) -> None:
        """BFX01-02 passes only when the instance is gone and the machine is held."""
        step_output = {
            "success": True,
            "operation": {
                "accepted": True,
                "instance_deleted": True,
                "machine_quarantined": True,
                "machine_id": "m-1",
            },
        }
        check = _run(ReturnNodeMaintenanceCheck, step_output)
        assert check.passed
        assert "m-1" in check.message

    def test_node_return_fails_when_the_instance_survives(self) -> None:
        """Nothing was returned if the instance is still there."""
        step_output = {
            "success": True,
            "operation": {"accepted": True, "instance_deleted": False, "machine_id": "m-1"},
        }
        assert not _run(ReturnNodeMaintenanceCheck, step_output).passed

    def test_node_return_fails_when_the_machine_goes_back_to_the_pool(self) -> None:
        """A node re-offered to the next tenant was deleted, not returned for maintenance.

        This is the half providers get wrong: a bare delete looks identical
        until you ask what happened to the machine afterwards.
        """
        step_output = {
            "success": True,
            "operation": {
                "accepted": True,
                "instance_deleted": True,
                "machine_quarantined": False,
                "machine_id": "m-1",
            },
        }
        check = _run(ReturnNodeMaintenanceCheck, step_output)
        assert not check.passed
        assert "allocatable pool" in check.message

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


def _log_host(**overrides: Any) -> dict[str, Any]:
    """Build a host record that satisfies the BFX03-03 log-history contract."""
    return {
        "host_id": "h-1",
        "window_start": "2026-06-24T00:00:00Z",
        "window_end": "2026-06-24T12:00:00Z",
        "entries_returned": 128,
        **overrides,
    }


class TestBmcKernelLogCheck:
    """Cover the BFX03-03 log-history check."""

    def test_passes_when_a_windowed_query_returns_entries(self) -> None:
        """Entries returned over a stated window is what makes it a history."""
        check = _run(BmcKernelLogCheck, {"success": True, "hosts": [_log_host()]})
        assert check.passed
        assert "128 entries" in check.message

    def test_fails_when_a_host_cannot_name_itself(self) -> None:
        """A host record with no host_id gives the tenant nothing to go and read."""
        host = _log_host()
        del host["host_id"]
        check = _run(BmcKernelLogCheck, {"success": True, "hosts": [host]})
        assert not check.passed
        assert "missing host_id" in check.message

    def test_fails_without_a_query_window(self) -> None:
        """Entries with no window could be a live tail rather than a history."""
        host = _log_host()
        del host["window_start"]
        check = _run(BmcKernelLogCheck, {"success": True, "hosts": [host]})
        assert not check.passed
        assert "query window" in check.message

    def test_fails_when_the_window_is_inverted(self) -> None:
        """A window ending before it starts was not a real query."""
        host = _log_host(window_start="2026-06-24T12:00:00Z", window_end="2026-06-24T00:00:00Z")
        assert not _run(BmcKernelLogCheck, {"success": True, "hosts": [host]}).passed

    def test_fails_when_no_entries_come_back(self) -> None:
        """A provider that answers with nothing has not demonstrated it can answer."""
        check = _run(BmcKernelLogCheck, {"success": True, "hosts": [_log_host(entries_returned=0)]})
        assert not check.passed
        assert "No log entries" in check.message


def _agents(*records: dict[str, Any], nodes_expected: int | None = None) -> dict[str, Any]:
    """Return a BFX04-01 step payload carrying ``records``.

    Defaults the declared fleet size to full coverage so each test states only
    the rule it is about; the coverage tests pass ``nodes_expected`` explicitly.
    """
    return {
        "success": True,
        "agents_observable": True,
        "nodes_expected": len(records) if nodes_expected is None else nodes_expected,
        "agents": list(records),
    }


class TestNodeHealthAgentCheck:
    """Cover the BFX04-01 GPU health monitoring process check."""

    def test_fails_when_agents_not_observable(self) -> None:
        """A platform that cannot observe health agents fails."""
        assert not _run(NodeHealthAgentCheck, {"success": True, "agents_observable": False, "agents": []}).passed

    def test_fails_when_no_agents_returned(self) -> None:
        """BFX04-01 needs evidence an agent is running; zero records is not that."""
        assert not _run(NodeHealthAgentCheck, {"success": True, "agents_observable": True, "agents": []}).passed

    def test_passes_and_names_the_agents_it_found(self) -> None:
        """Any agent name satisfies the check, and the result reports which ones."""
        check = _run(
            NodeHealthAgentCheck,
            _agents(
                {"node_id": "gpu-1", "agent_name": "nvsentinel", "running": True},
                {"node_id": "gpu-2", "agent_name": "gpud", "running": True},
            ),
        )
        assert check.passed
        assert "gpud" in check.message
        assert "nvsentinel" in check.message

    def test_passes_for_an_agent_the_check_has_never_heard_of(self) -> None:
        """The requirement is a health monitoring process, not a named product."""
        assert _run(
            NodeHealthAgentCheck, _agents({"node_id": "gpu-1", "agent_name": "acme-gpu-watch", "running": True})
        ).passed

    def test_fails_when_any_reported_node_lacks_a_running_agent(self) -> None:
        """One uncovered GPU node prevents a false partial-coverage pass."""
        check = _run(
            NodeHealthAgentCheck,
            _agents(
                {"node_id": "gpu-1", "agent_name": "nvsentinel", "running": True},
                {"node_id": "gpu-2", "agent_name": "", "running": False},
            ),
        )
        assert not check.passed
        assert "gpu-2" in check.message

    @pytest.mark.parametrize("running", ["false", "true", 1, None])
    def test_fails_when_running_is_not_a_boolean_true(self, running: object) -> None:
        """The contract says bool; "false" is a truthy string and must not pass."""
        check = _run(NodeHealthAgentCheck, _agents({"node_id": "gpu-1", "agent_name": "gpud", "running": running}))
        assert not check.passed
        assert "gpu-1" in check.message

    def test_fails_when_a_running_agent_is_unnamed(self) -> None:
        """``running`` with no agent_name is the provider's say-so, not evidence."""
        check = _run(NodeHealthAgentCheck, _agents({"node_id": "gpu-1", "running": True}))
        assert not check.passed
        assert "agent_name" in check.message

    def test_fails_when_a_record_cannot_name_its_node(self) -> None:
        """An agent nobody can locate gives an operator nothing to act on."""
        check = _run(NodeHealthAgentCheck, _agents({"agent_name": "nvsentinel", "running": True}))
        assert not check.passed
        assert "node_id" in check.message

    def test_fails_when_records_cover_only_part_of_the_fleet(self) -> None:
        """Probing 3 of 64 GPU nodes must not carry BFX04-01 for the whole site."""
        check = _run(
            NodeHealthAgentCheck,
            _agents({"node_id": "gpu-1", "agent_name": "gpud", "running": True}, nodes_expected=64),
        )
        assert not check.passed
        assert "1 of 64" in check.message

    def test_repeated_records_for_one_node_do_not_cover_a_fleet(self) -> None:
        """Coverage counts distinct nodes: one node_id restated is still one node.

        Counting records would let a provider repeat its single healthy node up to
        ``nodes_expected`` and satisfy the check that exists precisely because its
        own account of its coverage is not trusted.
        """
        check = _run(
            NodeHealthAgentCheck,
            _agents(
                {"node_id": "gpu-1", "agent_name": "gpud", "running": True},
                {"node_id": "gpu-1", "agent_name": "gpud", "running": True},
                {"node_id": " gpu-1 ", "agent_name": "gpud", "running": True},
                nodes_expected=3,
            ),
        )
        assert not check.passed
        assert "1 of 3" in check.message

    @pytest.mark.parametrize("expected", [None, 0, -1, "8", True])
    def test_fails_when_the_fleet_size_is_not_reported(self, expected: object) -> None:
        """Without a usable GPU node count the result cannot show fleet coverage."""
        step_output = _agents({"node_id": "gpu-1", "agent_name": "gpud", "running": True})
        if expected is None:
            del step_output["nodes_expected"]
        else:
            step_output["nodes_expected"] = expected

        check = _run(NodeHealthAgentCheck, step_output)
        assert not check.passed
        assert "nodes_expected" in check.message

    def test_passes_when_records_exceed_the_reported_fleet_size(self) -> None:
        """Extra records are over-coverage, not a coverage gap."""
        check = _run(
            NodeHealthAgentCheck,
            _agents(
                {"node_id": "gpu-1", "agent_name": "gpud", "running": True},
                {"node_id": "gpu-2", "agent_name": "gpud", "running": True},
                nodes_expected=1,
            ),
        )
        assert check.passed

    def test_skips_when_the_provider_reports_no_gpu_nodes(self) -> None:
        """No GPU nodes at the site is not applicable rather than failing."""
        step_output = _agents() | {"skipped": True, "skip_reason": "No GPU nodes detected"}
        with pytest.raises(pytest.skip.Exception, match="No GPU nodes detected"):
            _run(NodeHealthAgentCheck, step_output)


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
            "notifications": [
                {
                    "machine_id": "m-1",
                    "message": "scheduled",
                    "detected_at": "2026-06-24T11:59:30Z",
                    "notified_at": "2026-06-24T12:00:00Z",
                    "window_start": "2026-07-01T02:00:00Z",
                }
            ],
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


def _tray(**overrides: Any) -> dict[str, Any]:
    """Build a tray record that satisfies the BFX03-02 contract."""
    return {"tray_id": "nvsw-001", "firmware_version": "1.0.0", **overrides}


class TestNvSwitchFirmwareCheck:
    """Cover the BFX03-02 switch tray firmware check."""

    def test_passes_when_every_tray_reports_a_version(self) -> None:
        """A named tray with a firmware version is the passing case."""
        check = _run(NvSwitchFirmwareCheck, {"success": True, "trays": [_tray()]})
        assert check.passed
        assert "1 NV switch tray" in check.message

    def test_fails_when_a_tray_cannot_name_itself(self) -> None:
        """A version with no tray attached does not say which hardware to update."""
        tray = _tray()
        del tray["tray_id"]
        check = _run(NvSwitchFirmwareCheck, {"success": True, "trays": [tray]})
        assert not check.passed
        assert "missing tray_id" in check.message

    def test_fails_when_a_tray_reports_no_version(self) -> None:
        """The failure names the tray, so an operator knows where to look."""
        check = _run(NvSwitchFirmwareCheck, {"success": True, "trays": [_tray(firmware_version="")]})
        assert not check.passed
        assert "missing firmware_version" in check.message
        assert "nvsw-001" in check.message

    def test_fails_when_fewer_trays_than_required(self) -> None:
        """min_trays lets a suite demand more than one tray's worth of evidence."""
        check = NvSwitchFirmwareCheck(config={"step_output": {"success": True, "trays": [_tray()]}, "min_trays": 2})
        check.run()
        assert not check.passed

    def test_fails_when_the_trays_list_is_absent(self) -> None:
        """A step that reports no trays key has not answered the question."""
        assert not _run(NvSwitchFirmwareCheck, {"success": True}).passed
