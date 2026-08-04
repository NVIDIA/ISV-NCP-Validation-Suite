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
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from isvtest.core.validation import BaseValidation


def _record_label(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "unknown"


def _maybe_skip(step_output: dict[str, Any]) -> None:
    if step_output.get("skipped") is True:
        pytest.skip(step_output.get("skip_reason") or "Break-fix step skipped (not configured on this platform)")


def _require_success(step_output: dict[str, Any], check: BaseValidation) -> bool:
    """Return False when the step failed and the check should stop."""
    _maybe_skip(step_output)
    if step_output.get("success"):
        return True
    check.set_failed(step_output.get("error") or "Break-fix step failed")
    return False


class MaintenanceEventsCheck(BaseValidation):
    """Validate upcoming/current maintenance events are queryable (BFX02-01).

    Step output:
        success, events: list[{machine_id, hardware_id, status, message, opened_at?}]
        events_queryable: bool -- API exposes maintenance event records
    """

    description: ClassVar[str] = "Query upcoming or current maintenance events for a node"
    timeout: ClassVar[int] = 120

    def run(self) -> None:
        step_output = self.config.get("step_output", {})
        if not _require_success(step_output, self):
            return
        if not step_output.get("events_queryable"):
            self.set_failed("Maintenance events are not queryable via the break-fix API")
            return
        self.set_passed(
            f"Maintenance event query API available ({len(step_output.get('events') or [])} event(s) at site)"
        )


class RetirementNoticesCheck(BaseValidation):
    """Validate retirement notices for a node/rack are queryable (BFX02-02).

    Step output:
        success, notices_queryable: bool, notices: list[dict]
    """

    description: ClassVar[str] = "Query retirement notices for a node or rack"
    timeout: ClassVar[int] = 120

    def run(self) -> None:
        step_output = self.config.get("step_output", {})
        if not _require_success(step_output, self):
            return
        if not step_output.get("notices_queryable"):
            self.set_failed("Retirement notices are not queryable via the break-fix API")
            return
        self.set_passed(
            f"Retirement notice query API available ({len(step_output.get('notices') or [])} notice(s) at site)"
        )


class RepairHistoryCheck(BaseValidation):
    """Validate historical repair status is queryable for a node (BFX02-03).

    Step output:
        success, history_queryable: bool, records: list[{machine_id, entries: list[dict]}]
    """

    description: ClassVar[str] = "Query historical repair status for a node"
    timeout: ClassVar[int] = 120

    def run(self) -> None:
        step_output = self.config.get("step_output", {})
        if not _require_success(step_output, self):
            return
        if not step_output.get("history_queryable"):
            self.set_failed("Repair history is not queryable via the break-fix API")
            return
        records = step_output.get("records") or []
        self.set_passed(f"Repair history query API available ({len(records)} machine record(s))")


class NvSwitchFirmwareCheck(BaseValidation):
    """Validate NV switch tray firmware versions are inspectable (BFX03-02).

    Step output:
        success, trays: list[{tray_id, firmware_version}]
    """

    description: ClassVar[str] = "Inspect firmware versions of NV switch trays"
    timeout: ClassVar[int] = 120

    def run(self) -> None:
        step_output = self.config.get("step_output", {})
        if not _require_success(step_output, self):
            return
        trays = step_output.get("trays")
        if not isinstance(trays, list):
            self.set_failed("Switch firmware step output is missing the 'trays' list")
            return
        min_trays = self._parse_positive_int("min_trays", default=1)
        if min_trays is None:
            return
        missing = [t for t in trays if not (isinstance(t, dict) and (t.get("firmware_version") or "").strip())]
        if missing:
            self.set_failed(f"{len(missing)} switch tray(s) missing firmware_version")
            return
        if len(trays) < min_trays:
            self.set_failed(f"Expected at least {min_trays} NV switch tray(s), got {len(trays)}")
            return
        self.set_passed(f"Firmware version queryable for {len(trays)} NV switch tray(s)")


class BmcKernelLogCheck(BaseValidation):
    """Validate BMC kernel log messages are obtainable for a node (BFX03-03).

    Step output:
        success, hosts: list[{host_id, kernel_log_available: bool, entry_count: int}]
    """

    description: ClassVar[str] = "Obtain BMC kernel log messages for a node"
    timeout: ClassVar[int] = 120

    def run(self) -> None:
        step_output = self.config.get("step_output", {})
        if not _require_success(step_output, self):
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
        unavailable = [h for h in hosts if not h.get("kernel_log_available")]
        if unavailable:
            labels = ", ".join(_record_label(h, "host_id", "machine_id") for h in unavailable[:3])
            self.set_failed(f"BMC kernel logs unavailable for {len(unavailable)} host(s): {labels}")
            return
        self.set_passed(f"BMC kernel logs obtainable for {len(hosts)} host(s)")


class GpuResetCheck(BaseValidation):
    """Validate GPU reset via the break-fix API (BFX01-01).

    Step output:
        success, operation: {requested, completed, node_id}
    """

    description: ClassVar[str] = "Reset GPUs on an individual node via the breakfix API"
    timeout: ClassVar[int] = 600

    def run(self) -> None:
        step_output = self.config.get("step_output", {})
        if not _require_success(step_output, self):
            return
        operation = step_output.get("operation") or {}
        if not operation.get("completed"):
            self.set_failed(operation.get("message") or "GPU reset did not complete")
            return
        self.set_passed(f"GPU reset completed for node {_record_label(operation, 'node_id', 'machine_id')}")


class ReturnNodeMaintenanceCheck(BaseValidation):
    """Validate returning an individual node for maintenance (BFX01-02).

    Step output:
        success, operation: {requested, accepted, machine_id, maintenance_mode}
    """

    description: ClassVar[str] = "Return an individual node to the provider for maintenance via the API"
    timeout: ClassVar[int] = 600

    def run(self) -> None:
        step_output = self.config.get("step_output", {})
        if not _require_success(step_output, self):
            return
        operation = step_output.get("operation") or {}
        if not operation.get("accepted"):
            self.set_failed(operation.get("message") or "Node maintenance return was not accepted")
            return
        self.set_passed(
            f"Node {_record_label(operation, 'machine_id', 'node_id')} accepted for maintenance "
            f"(maintenance_mode={operation.get('maintenance_mode')})"
        )


class ReturnRackMaintenanceCheck(BaseValidation):
    """Validate returning a rack for maintenance (BFX01-03).

    Step output:
        success, operation: {requested, accepted, rack_id}
    """

    description: ClassVar[str] = "Return a rack to the provider for maintenance via the API"
    timeout: ClassVar[int] = 600

    def run(self) -> None:
        step_output = self.config.get("step_output", {})
        if not _require_success(step_output, self):
            return
        operation = step_output.get("operation") or {}
        if not operation.get("accepted"):
            self.set_failed(operation.get("message") or "Rack maintenance return was not accepted")
            return
        self.set_passed(f"Rack {_record_label(operation, 'rack_id')} accepted for maintenance")


class CordonNodeCheck(BaseValidation):
    """Validate cordon: unschedulable with existing workloads continuing (BFX01-04).

    Step output:
        success, operation: {cordoned, new_workloads_blocked, existing_workloads_running}
    """

    description: ClassVar[str] = "Cordon a node and verify scheduling behavior"
    timeout: ClassVar[int] = 600

    def run(self) -> None:
        step_output = self.config.get("step_output", {})
        if not _require_success(step_output, self):
            return
        operation = step_output.get("operation") or {}
        if not operation.get("cordoned"):
            self.set_failed(operation.get("message") or "Node was not cordoned")
            return
        if not operation.get("new_workloads_blocked"):
            self.set_failed("New workloads were not blocked on the cordoned node")
            return
        if operation.get("existing_workloads_running") is False:
            self.set_failed("Existing workloads did not continue on the cordoned node")
            return
        self.set_passed("Node cordoned: new workloads blocked, existing workloads continue")


class HostReplacementCheck(BaseValidation):
    """Validate host replacement when health thresholds are breached (BFX01-05).

    Step output:
        success, operation: {requested, node_removed_from_pool, machine_id}
    """

    description: ClassVar[str] = "Request host replacement and verify node removed from pool"
    timeout: ClassVar[int] = 900

    def run(self) -> None:
        step_output = self.config.get("step_output", {})
        if not _require_success(step_output, self):
            return
        operation = step_output.get("operation") or {}
        if not operation.get("node_removed_from_pool"):
            self.set_failed(operation.get("message") or "Node was not removed from the allocatable pool")
            return
        self.set_passed(f"Host replacement removed {_record_label(operation, 'machine_id', 'node_id')} from the pool")


class NodeHealthAgentCheck(BaseValidation):
    """Validate GPUd or Sentinel (node health agent) is running (BFX04-01).

    Step output:
        success, agents: list[{node_id, agent_name, running: bool}]
        agents_observable: bool
    """

    description: ClassVar[str] = "Check that GPUd or Sentinel is running"
    timeout: ClassVar[int] = 120

    def run(self) -> None:
        step_output = self.config.get("step_output", {})
        if not _require_success(step_output, self):
            return
        if not step_output.get("agents_observable"):
            self.set_failed("Node health agents (GPUd/Sentinel) are not observable on this platform")
            return
        agents = step_output.get("agents") or []
        not_running = [a for a in agents if isinstance(a, dict) and not a.get("running")]
        if not_running:
            labels = ", ".join(_record_label(a, "node_id", "machine_id") for a in not_running[:3])
            self.set_failed(f"Health agent not running on {len(not_running)} node(s): {labels}")
            return
        self.set_passed(f"Node health agent running on {len(agents)} node(s)")


class PlannedMaintenanceNotificationCheck(BaseValidation):
    """Validate tenants can be notified of planned maintenance (BFX05-01).

    Step output:
        success, notification_channel_observable: bool, sample_event: dict | null
    """

    description: ClassVar[str] = "Verify tenants can be notified of planned future node maintenance"
    timeout: ClassVar[int] = 120

    def run(self) -> None:
        step_output = self.config.get("step_output", {})
        if not _require_success(step_output, self):
            return
        if not step_output.get("notification_channel_observable"):
            self.set_failed("Planned maintenance notification channel is not observable")
            return
        self.set_passed("Planned maintenance notification channel is available")


class FailureNotificationCheck(BaseValidation):
    """Validate tenants can be notified of immediate node failure (BFX06-01).

    Step output:
        success, notification_channel_observable: bool, sample_event: dict | null
    """

    description: ClassVar[str] = "Verify tenants can be notified of immediate node failure"
    timeout: ClassVar[int] = 120

    def run(self) -> None:
        step_output = self.config.get("step_output", {})
        if not _require_success(step_output, self):
            return
        if not step_output.get("notification_channel_observable"):
            self.set_failed("Immediate failure notification channel is not observable")
            return
        self.set_passed("Immediate failure notification channel is available")
