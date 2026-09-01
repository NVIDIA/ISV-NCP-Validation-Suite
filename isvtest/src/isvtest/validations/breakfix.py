# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Break-fix / break-fix validations (BFX01-BFX06).

Provider-agnostic checks over step JSON output. Lifecycle steps may emit
``skipped`` when a platform lacks the mutating break-fix API (for example
Maestro/GPUd integrations not yet wired). Query steps assert observability
of maintenance, repair, and diagnostic signals where the provider exposes them.

Every "is this signal observable" requirement (BFX02, BFX05, BFX06) is held to
the same evidence bar by ``_QueryableRecordsCheck``: the provider must report
the signal as observable *and* return at least one record demonstrating it. A
self-declared boolean is not evidence -- a provider could emit it for an API it
never called -- so a capability claimed with no records skips rather than
passes, and the requirement stays visibly unproven.

Several checks here are *empty shells*: the class and its JSON contract exist,
but no provider implements the capability yet, so the contract is the whole
deliverable -- it is what an ISV would implement against.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar

import pytest

from isvtest.core.validation import BaseValidation

UNKNOWN_LABEL = "unknown"


def _record_label(record: dict[str, Any], *keys: str) -> str:
    """Return the first non-blank string value among ``keys``, or ``"unknown"``."""
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return UNKNOWN_LABEL


def _has_fields(record: Any, *fields: str) -> bool:
    """Return whether ``record`` carries every field with a non-empty value."""
    if not isinstance(record, dict):
        return False
    return all(str(record.get(field) or "").strip() for field in fields)


def _timestamp(record: dict[str, Any], field: str) -> datetime | None:
    """Parse an ISO 8601 timestamp from ``record``, or None when absent/malformed.

    A timestamp that cannot be parsed is treated as missing rather than as an
    error: these fields exist to be compared, and one that cannot be compared
    evidences nothing.
    """
    try:
        parsed = datetime.fromisoformat(str(record.get(field) or ""))
    except ValueError:
        return None
    # Mixed offset-aware and naive values cannot be compared; normalise to UTC.
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _ordered(record: Any, earlier: str, later: str) -> bool:
    """Return whether ``record`` carries both timestamps and they are in order."""
    if not isinstance(record, dict):
        return False
    first, second = _timestamp(record, earlier), _timestamp(record, later)
    return first is not None and second is not None and first <= second


def _step_output(check: BaseValidation) -> dict[str, Any] | None:
    """Return the step payload, or None when the check should stop.

    Skips when the provider step reported a structured skip, and fails the check
    when the step itself failed. ``BaseValidation.execute`` also honours
    ``skipped`` before calling ``run``; repeating it here keeps a directly
    invoked ``run`` consistent with the sibling validation modules.
    """
    step_output = check.config.get("step_output", {})
    if step_output.get("skipped") is True:
        pytest.skip(step_output.get("skip_reason") or "Break-fix step skipped (not configured on this platform)")
    if not step_output.get("success"):
        check.set_failed(step_output.get("error") or "Break-fix step failed")
        return None
    return step_output


class _QueryableRecordsCheck(BaseValidation):
    """Shared machinery for the "is this signal observable" checks.

    Subclasses supply the step-output keys and the wording; the policy is the
    same for all of them: the provider must report the signal as observable,
    and must return at least one record that actually demonstrates it. A list
    with no usable records skips rather than passes, because a site with no
    records is indistinguishable from one with no API at all -- a pass there
    would assert nothing beyond the provider's own say-so.
    """

    _exclude_from_discovery: ClassVar[bool] = True
    timeout: ClassVar[int] = 120

    queryable_key: ClassVar[str]
    records_key: ClassVar[str]
    unavailable_message: ClassVar[str]
    absent_noun: ClassVar[str]
    api_label: ClassVar[str]
    record_noun: ClassVar[str]
    # Fields a record must carry to count. Empty means "any non-empty record",
    # which only suits signals whose mere existence is the evidence.
    evidence_fields: ClassVar[tuple[str, ...]] = ()

    def _is_evidence(self, record: Any) -> bool:
        """Return whether one record demonstrates the signal.

        A record missing the fields that make it actionable is not evidence that
        the API works -- it is evidence that something answered. Subclasses
        override instead when the rule is not a flat list of required fields.
        """
        if not record:
            return False
        return _has_fields(record, *self.evidence_fields) if self.evidence_fields else True

    def run(self) -> None:
        """Assert the signal is reported observable and backed by real records."""
        step_output = _step_output(self)
        if step_output is None:
            return
        if not step_output.get(self.queryable_key):
            self.set_failed(self.unavailable_message)
            return
        records = [r for r in (step_output.get(self.records_key) or []) if self._is_evidence(r)]
        if not records:
            pytest.skip(f"No {self.absent_noun} at the site; the query API cannot be demonstrated")
        self.set_passed(f"{self.api_label} query API returned {len(records)} {self.record_noun}(s)")


class MaintenanceEventsCheck(_QueryableRecordsCheck):
    """Validate upcoming/current maintenance events are queryable (BFX02-01).

    Step output:
        success, events: list[{machine_id, status, message}]
        events_queryable: bool -- API exposes maintenance event records
    """

    description: ClassVar[str] = "Query upcoming or current maintenance events for a node"

    queryable_key: ClassVar[str] = "events_queryable"
    records_key: ClassVar[str] = "events"
    unavailable_message: ClassVar[str] = "Maintenance events are not queryable via the break-fix API"
    absent_noun: ClassVar[str] = "maintenance events"
    api_label: ClassVar[str] = "Maintenance event"
    record_noun: ClassVar[str] = "event"


class RetirementNoticesCheck(_QueryableRecordsCheck):
    """Validate retirement notices for a node/rack are queryable (BFX02-02).

    Empty shell: no provider exposes retirement notices, which need enough lead
    time for the tenant to migrate off the hardware to be worth anything.

    Step output:
        success, notices_queryable: bool
        notices: list[{machine_id | rack_id, retire_after, status?, message?}]
    """

    description: ClassVar[str] = "Query retirement notices for a node or rack"

    queryable_key: ClassVar[str] = "notices_queryable"
    records_key: ClassVar[str] = "notices"
    unavailable_message: ClassVar[str] = "Retirement notices are not queryable via the break-fix API"
    absent_noun: ClassVar[str] = "retirement notices"
    api_label: ClassVar[str] = "Retirement notice"
    record_noun: ClassVar[str] = "notice"

    def _is_evidence(self, record: Any) -> bool:
        """A notice needs a subject and a date, or the tenant cannot act on it.

        Either identifier will do -- providers retire whole racks as readily as
        single machines -- but ``retire_after`` is what makes it a notice rather
        than a statement that something will be retired eventually.
        """
        if not _has_fields(record, "retire_after"):
            return False
        return _has_fields(record, "machine_id") or _has_fields(record, "rack_id")


class RepairHistoryCheck(_QueryableRecordsCheck):
    """Validate historical repair status is queryable for a node (BFX02-03).

    Step output:
        success, history_queryable: bool, records: list[{machine_id, entries: list[dict]}]
    """

    description: ClassVar[str] = "Query historical repair status for a node"

    queryable_key: ClassVar[str] = "history_queryable"
    records_key: ClassVar[str] = "records"
    unavailable_message: ClassVar[str] = "Repair history is not queryable via the break-fix API"
    absent_noun: ClassVar[str] = "repair history"
    api_label: ClassVar[str] = "Repair history"
    record_noun: ClassVar[str] = "machine record"

    def _is_evidence(self, record: Any) -> bool:
        """A machine record proves nothing without at least one history entry."""
        return bool(isinstance(record, dict) and record.get("entries"))


class NvSwitchFirmwareCheck(BaseValidation):
    """Validate NV switch tray firmware versions are inspectable (BFX03-02).

    Partial: NICo holds tray firmware but exposes it only to provider admins,
    while the requirement asks for something a tenant can inspect. The provider
    step reports that split itself -- data on provider credentials, a structured
    skip naming the gap on tenant credentials -- so this check only ever judges
    the half that answered.

    A tray must identify itself as well as report a version, for the same reason
    a log-history host must (BFX03-03): a version with no tray attached tells an
    operator nothing about which hardware to go and update.

    Step output:
        success, trays: list[{tray_id, firmware_version}]
    """

    description: ClassVar[str] = "Inspect firmware versions of NV switch trays"
    timeout: ClassVar[int] = 120

    def run(self) -> None:
        """Assert every reported NV switch tray exposes a firmware version."""
        step_output = _step_output(self)
        if step_output is None:
            return
        trays = step_output.get("trays")
        if not isinstance(trays, list):
            self.set_failed("Switch firmware step output is missing the 'trays' list")
            return
        min_trays = self._parse_positive_int("min_trays", default=1)
        if min_trays is None:
            return
        unidentified = [t for t in trays if not _has_fields(t, "tray_id")]
        if unidentified:
            self.set_failed(f"{len(unidentified)} switch tray(s) missing tray_id")
            return
        missing = [t for t in trays if not _has_fields(t, "firmware_version")]
        if missing:
            labels = ", ".join(_record_label(t, "tray_id") for t in missing[:3])
            self.set_failed(f"{len(missing)} switch tray(s) missing firmware_version: {labels}")
            return
        if len(trays) < min_trays:
            self.set_failed(f"Expected at least {min_trays} NV switch tray(s), got {len(trays)}")
            return
        self.set_passed(f"Firmware version queryable for {len(trays)} NV switch tray(s)")


class BmcKernelLogCheck(BaseValidation):
    """Validate a node's log history is queryable through a telemetry endpoint (BFX03-03).

    Empty shell: reframed from serial-over-LAN BMC console access to a queryable
    log history or stream (OTEL, or an OpenSearch/Kibana equivalent), which no
    provider exposes. The class name is a leftover from the original framing,
    kept because the check is released.

    The contract asks a provider to prove it can answer a question, not to
    declare that it could. A boolean "logs are available" is satisfiable by any
    provider that returns ``true`` and builds nothing, so instead a host must
    report the window it was asked about and how many entries came back -- the
    window is what makes it a *history* rather than a live tail.

    Step output:
        success, hosts: list[{host_id, window_start, window_end, entries_returned: int}]
    """

    description: ClassVar[str] = "Query a node's log history through a telemetry endpoint"
    timeout: ClassVar[int] = 120

    def run(self) -> None:
        """Assert BMC kernel logs are obtainable for every reported host."""
        step_output = _step_output(self)
        if step_output is None:
            return
        hosts = step_output.get("hosts")
        if not isinstance(hosts, list):
            self.set_failed("BMC kernel log step output is missing the 'hosts' list")
            return
        min_hosts = self._parse_positive_int("min_hosts", default=1)
        if min_hosts is None:
            return
        if len(hosts) < min_hosts:
            self.set_failed(f"Expected at least {min_hosts} host(s), got {len(hosts)}")
            return
        # A host that cannot name itself gives the tenant nothing to go and read.
        unidentified = [h for h in hosts if not _has_fields(h, "host_id")]
        if unidentified:
            self.set_failed(f"{len(unidentified)} host record(s) missing host_id")
            return
        unwindowed = [h for h in hosts if not _ordered(h, "window_start", "window_end")]
        if unwindowed:
            labels = ", ".join(_record_label(h, "host_id", "machine_id") for h in unwindowed[:3])
            self.set_failed(
                f"{len(unwindowed)} host(s) did not report an ordered query window (window_start, window_end): {labels}"
            )
            return
        empty = [h for h in hosts if not isinstance(h.get("entries_returned"), int) or h["entries_returned"] < 1]
        if empty:
            labels = ", ".join(_record_label(h, "host_id", "machine_id") for h in empty[:3])
            self.set_failed(f"No log entries returned for {len(empty)} host(s) over the queried window: {labels}")
            return
        total = sum(h["entries_returned"] for h in hosts)
        self.set_passed(f"Log history queryable for {len(hosts)} host(s); {total} entries returned")


class _OperationCheck(BaseValidation):
    """Shared machinery for the BFX01 mutating-operation checks.

    Subclasses name the ``operation`` flag that marks the operation as having
    taken effect and supply the wording. The provider's own ``operation.message``
    wins over the generic failure text when the operation did not take effect.
    """

    _exclude_from_discovery: ClassVar[bool] = True
    timeout: ClassVar[int] = 600

    completion_key: ClassVar[str]
    failure_message: ClassVar[str]
    label_keys: ClassVar[tuple[str, ...]]
    pass_template: ClassVar[str]

    def _pass_message(self, label: str, operation: dict[str, Any]) -> str:
        """Return the success message for a completed operation."""
        return self.pass_template.format(label=label)

    def _finish(self, operation: dict[str, Any]) -> None:
        """Pass the check, unless the operation cannot say what it acted on.

        A provider that reports success without naming the resource has not
        demonstrated the operation reached anything in particular, and the
        message would read "... for node unknown", which is not a result.
        """
        label = _record_label(operation, *self.label_keys)
        if label == UNKNOWN_LABEL:
            self.set_failed(
                "Operation reported success without identifying what it acted on "
                f"(expected one of: {', '.join(self.label_keys)})"
            )
            return
        self.set_passed(self._pass_message(label, operation))

    def run(self) -> None:
        """Assert the provider reported the operation as having taken effect."""
        step_output = _step_output(self)
        if step_output is None:
            return
        operation = step_output.get("operation") or {}
        if not operation.get(self.completion_key):
            self.set_failed(operation.get("message") or self.failure_message)
            return
        self._finish(operation)


class GpuResetCheck(_OperationCheck):
    """Validate a requested GPU reset on an operator-managed node (BFX01-01).

    Empty shell: no provider exposes an on-demand GPU reset, so there is no
    synchronous request to make; reporting the node as needing repair instead is
    BFX01-06 (``ReportNodeRepairCheck``).

    The contract is deliberately asynchronous. A reset runs through provider
    automation that polls for work and can then wait on human intervention, so
    a synchronous ``completed`` flag would be asserting something no provider
    can honour. What a tenant can be owed is that the request is accepted, is
    scoped to named GPUs, and comes back with a handle to poll -- completion is
    observed later, out of band, and is not this check's business.

    Step output:
        success, operation: {accepted, node_id, gpu_ids: list[str], request_id}
    """

    description: ClassVar[str] = "Request a reset of GPUs on an operator-managed node"

    completion_key: ClassVar[str] = "accepted"
    failure_message: ClassVar[str] = "GPU reset request was not accepted"
    label_keys: ClassVar[tuple[str, ...]] = ("node_id", "machine_id")
    pass_template: ClassVar[str] = "GPU reset requested for node {label}"

    def _finish(self, operation: dict[str, Any]) -> None:
        """Require the request be trackable and scoped before calling it accepted."""
        if not _has_fields(operation, "request_id"):
            self.set_failed("GPU reset was accepted without a request_id; the tenant cannot poll it to completion")
            return
        if not [g for g in (operation.get("gpu_ids") or []) if str(g).strip()]:
            self.set_failed("GPU reset was accepted without naming any GPU in gpu_ids")
            return
        super()._finish(operation)

    def _pass_message(self, label: str, operation: dict[str, Any]) -> str:
        """Name the GPUs the request covered and the handle that tracks it."""
        gpus = [g for g in (operation.get("gpu_ids") or []) if str(g).strip()]
        return f"{super()._pass_message(label, operation)}: {len(gpus)} GPU(s), request {operation['request_id']}"


class ReturnNodeMaintenanceCheck(_OperationCheck):
    """Validate returning an individual node for maintenance (BFX01-02).

    The destructive counterpart to ``ReportNodeRepairCheck`` (BFX01-06): the
    tenant is relinquishing the node rather than keeping it, so the instance is
    destroyed and does not come back.

    Two things have to be true, and the second is the one providers get wrong.
    The instance must be gone -- otherwise nothing was returned -- and the
    machine must not have gone straight back into the allocatable pool. A node
    handed back "for maintenance" that is immediately offered to the next tenant
    was not returned for maintenance; it was just deleted, and whatever prompted
    the return is now someone else's problem.

    Step output:
        success, operation: {requested, accepted, instance_deleted,
        machine_quarantined, instance_id, machine_id}
    """

    description: ClassVar[str] = "Return an individual node to the provider for maintenance via the API"

    completion_key: ClassVar[str] = "instance_deleted"
    failure_message: ClassVar[str] = "Instance was not deleted, so the node was not returned"
    label_keys: ClassVar[tuple[str, ...]] = ("machine_id", "node_id")
    pass_template: ClassVar[str] = "Node {label} returned for maintenance"

    not_quarantined_message: ClassVar[str] = (
        "Node was returned but went back into the allocatable pool instead of being held for repair"
    )

    def _finish(self, operation: dict[str, Any]) -> None:
        """Require the machine to have left service, not just the instance to be gone."""
        if not operation.get("machine_quarantined"):
            self.set_failed(operation.get("message") or self.not_quarantined_message)
            return
        super()._finish(operation)


class ReturnRackMaintenanceCheck(_OperationCheck):
    """Validate returning a rack for maintenance (BFX01-03).

    Empty shell: no provider exposes rack-level maintenance handover, which has
    to return every node in the rack as one operation to mean anything.

    Step output:
        success, operation: {requested, accepted, rack_id}
    """

    description: ClassVar[str] = "Return a rack to the provider for maintenance via the API"

    completion_key: ClassVar[str] = "accepted"
    failure_message: ClassVar[str] = "Rack maintenance return was not accepted"
    label_keys: ClassVar[tuple[str, ...]] = ("rack_id",)
    pass_template: ClassVar[str] = "Rack {label} accepted for maintenance"


class HostReplacementCheck(_OperationCheck):
    """Validate host replacement when health thresholds are breached (BFX01-05).

    Empty shell, and the missing piece is the trigger rather than the API: no
    provider publishes the health thresholds that are supposed to be breached,
    so there is no condition to induce.

    Step output:
        success, operation: {requested, node_removed_from_pool, machine_id}
    """

    description: ClassVar[str] = "Request host replacement and verify node removed from pool"
    timeout: ClassVar[int] = 900

    completion_key: ClassVar[str] = "node_removed_from_pool"
    failure_message: ClassVar[str] = "Node was not removed from the allocatable pool"
    label_keys: ClassVar[tuple[str, ...]] = ("machine_id", "node_id")
    pass_template: ClassVar[str] = "Host replacement removed {label} from the pool"


class ReportNodeRepairCheck(_OperationCheck):
    """Validate reporting a node to the provider for maintenance (BFX01-06).

    The non-destructive counterpart to ``ReturnNodeMaintenanceCheck`` (BFX01-02):
    the tenant keeps the node and its workload while flagging that it needs repair
    eventually. So the pass condition is that the provider *acted* on the report by
    moving the node into a repair state, not that the node was handed back.

    Keying on the state change rather than on acceptance is deliberate. A 200 proves
    only that the endpoint exists; the tenant-visible contract is that the provider
    records the complaint against the node.

    It claims nothing about the repair itself. Providers run repair automation
    asynchronously -- typically minutes to weeks later, out of band from any API
    response -- so no synchronous check can observe a fix.

    Reporting a node is only non-destructive if the node comes back, so ``restored``
    is part of the pass condition rather than incidental cleanup. This is the only
    BFX01 check whose step is expected to undo itself, hence the extra condition on
    top of ``_OperationCheck``.

    Step output:
        success, operation: {requested, repair_state_observed, restored, node_id}
    """

    description: ClassVar[str] = "Report an individual node to the provider for maintenance via the API"

    completion_key: ClassVar[str] = "repair_state_observed"
    failure_message: ClassVar[str] = "Provider did not move the node into a repair state after the report"
    label_keys: ClassVar[tuple[str, ...]] = ("node_id", "machine_id")
    pass_template: ClassVar[str] = "Node {label} reported for repair; provider moved it into a repair state"

    not_restored_message: ClassVar[str] = (
        "Node was left in a repair state; the report was accepted but the node was not returned to the pool"
    )

    def run(self) -> None:
        """Assert the node entered a repair state *and* was taken back out of it."""
        step_output = _step_output(self)
        if step_output is None:
            return
        operation = step_output.get("operation") or {}
        if not operation.get(self.completion_key):
            self.set_failed(operation.get("message") or self.failure_message)
            return
        if not operation.get("restored"):
            # A step that reports its own restore failure already fails via
            # ``success``. This catches the cases that do not: a provider whose
            # step forgot to, and --skip-restore, which strands the node by design.
            self.set_failed(self.not_restored_message)
            return
        self._finish(operation)

    def _pass_message(self, label: str, operation: dict[str, Any]) -> str:
        """Append any provider finding raised while the node was taken back out of repair."""
        message = super()._pass_message(label, operation)
        detail = operation.get("message")
        return f"{message} ({detail})" if detail else message


class CordonNodeCheck(BaseValidation):
    """Validate cordon: unschedulable with existing workloads continuing (BFX01-04).

    Step output:
        success, operation: {cordoned, new_workloads_blocked, existing_workloads_running}
    """

    description: ClassVar[str] = "Cordon a node and verify scheduling behavior"
    timeout: ClassVar[int] = 600

    def run(self) -> None:
        """Assert the node is cordoned, blocks new work, and keeps existing work running."""
        step_output = _step_output(self)
        if step_output is None:
            return
        operation = step_output.get("operation") or {}
        if not operation.get("cordoned"):
            self.set_failed(operation.get("message") or "Node was not cordoned")
            return
        if not operation.get("new_workloads_blocked"):
            self.set_failed("New workloads were not blocked on the cordoned node")
            return
        if operation.get("existing_workloads_running") is not True:
            self.set_failed("Existing workloads were not confirmed still running on the cordoned node")
            return
        self.set_passed("Node cordoned: new workloads blocked, existing workloads continue")


class NodeHealthAgentCheck(BaseValidation):
    """Validate a GPU health monitoring process is running on every node (BFX04-01).

    Deliberately agent-neutral. The requirement originally named GPUd and NV
    Sentinel, but a test written against a named product outlives the product,
    and either could be cancelled; what a tenant is owed is that *something* is
    watching GPU health. So this check never matches on a name -- the provider's
    step decides which processes count on its platform and reports the one it
    found there.

    Which is why ``agent_name`` is required rather than merely documented. Once
    the name is not matched, it is the only thing separating a real probe from a
    hardcoded ``true``: a record of ``{"running": true}`` is the provider
    asserting its own capability, the same say-so the BFX02/BFX05/BFX06 checks
    refuse. It is also what makes the result actionable, since an operator
    reading "a process is running" cannot tell whether it is the right one.

    ``agents`` is expected to cover every GPU node the platform has, not just the
    ones the step was configured with or could reach. A step that reports a single
    healthy node and silently omits the rest passes while proving nothing about
    the fleet, so a node with nothing running belongs in the list as
    ``running: false`` -- and may omit ``agent_name``, having none to report --
    rather than being dropped. A site with no GPU nodes at all is the one case
    with nothing to assert, and is a structured skip rather than an empty list.

    Step output:
        success, agents: list[{node_id, agent_name, running: bool}]
        agents_observable: bool
    """

    description: ClassVar[str] = "Check that a GPU health monitoring process is running"
    timeout: ClassVar[int] = 120

    def run(self) -> None:
        """Assert every node reports a named GPU health monitoring process, running."""
        step_output = _step_output(self)
        if step_output is None:
            return
        if not step_output.get("agents_observable"):
            self.set_failed("GPU health monitoring processes are not observable on this platform")
            return
        agents = [a for a in (step_output.get("agents") or []) if isinstance(a, dict)]
        if not agents:
            self.set_failed("No health monitoring process records returned; none is running")
            return
        # Checked before the running state so the failures below can name nodes.
        unidentified = [a for a in agents if not _has_fields(a, "node_id")]
        if unidentified:
            self.set_failed(f"{len(unidentified)} health agent record(s) missing node_id")
            return
        not_running = [a for a in agents if not a.get("running")]
        if not_running:
            labels = ", ".join(_record_label(a, "node_id", "machine_id") for a in not_running[:3])
            self.set_failed(f"No GPU health monitoring process running on {len(not_running)} node(s): {labels}")
            return
        # Only demanded of running records: a node with nothing running has no
        # name to report, and it already failed above.
        unnamed = [a for a in agents if not _has_fields(a, "agent_name")]
        if unnamed:
            labels = ", ".join(_record_label(a, "node_id", "machine_id") for a in unnamed[:3])
            self.set_failed(
                f"{len(unnamed)} node(s) reported a running health monitoring process "
                f"without naming it in agent_name: {labels}"
            )
            return
        names = sorted({str(a["agent_name"]).strip() for a in agents})
        self.set_passed(f"GPU health monitoring process running on {len(agents)} node(s): {', '.join(names[:3])}")


class PlannedMaintenanceNotificationCheck(_QueryableRecordsCheck):
    """Validate tenants can be notified of planned maintenance (BFX05-01).

    Step output:
        success, notification_channel_observable: bool
        notifications: list[{machine_id, type, message, notified_at, window_start}]

    Requires a real notification record, not just the observable flag: the flag
    alone is the provider asserting its own capability.

    Empty shell: no provider exposes a maintenance notification channel, which
    needs to arrive far enough ahead of the window to drain workloads first.

    Lead time is the whole value here, and it takes two timestamps to show:
    ``notified_at`` alone proves only that something arrived. ``window_start``
    is what it has to arrive before. How much warning is *enough* is a number
    nobody has set yet, so the check demands only that the notice precede the
    window; a minimum lead time is the natural parameter to add once agreed.
    """

    description: ClassVar[str] = "Verify tenants can be notified of planned future node maintenance"

    queryable_key: ClassVar[str] = "notification_channel_observable"
    records_key: ClassVar[str] = "notifications"
    unavailable_message: ClassVar[str] = "Planned maintenance notification channel is not observable"
    absent_noun: ClassVar[str] = "planned maintenance notifications"
    api_label: ClassVar[str] = "Planned maintenance notification"
    record_noun: ClassVar[str] = "notification"
    evidence_fields: ClassVar[tuple[str, ...]] = ("machine_id",)

    def _is_evidence(self, record: Any) -> bool:
        """A notice must name a machine and land before the window it warns about."""
        return super()._is_evidence(record) and _ordered(record, "notified_at", "window_start")


class FailureNotificationCheck(_QueryableRecordsCheck):
    """Validate tenants can be notified of immediate node failure (BFX06-01).

    Step output:
        success, notification_channel_observable: bool
        notifications: list[{machine_id, type, message, detected_at, notified_at}]

    Requires a real notification record, for the same reason as
    PlannedMaintenanceNotificationCheck.

    Empty shell: no provider exposes a failure notification channel, where the
    contract is latency rather than lead time, there being no window to plan for.

    Latency also takes two timestamps, but the pair differs: a failure is
    measured from ``detected_at``, when the provider knew, to ``notified_at``,
    when it said so. Without the first, "immediate" is unfalsifiable. As with
    BFX05-01 the acceptable bound is unset, so only the ordering is enforced.
    """

    description: ClassVar[str] = "Verify tenants can be notified of immediate node failure"

    queryable_key: ClassVar[str] = "notification_channel_observable"
    records_key: ClassVar[str] = "notifications"
    unavailable_message: ClassVar[str] = "Immediate failure notification channel is not observable"
    absent_noun: ClassVar[str] = "immediate failure notifications"
    api_label: ClassVar[str] = "Immediate failure notification"
    record_noun: ClassVar[str] = "notification"
    evidence_fields: ClassVar[tuple[str, ...]] = ("machine_id",)

    def _is_evidence(self, record: Any) -> bool:
        """A failure notice must name a machine and be sent after detection."""
        return super()._is_evidence(record) and _ordered(record, "detected_at", "notified_at")
