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

"""Governance and capacity-fleet API validations.

Three provider-agnostic checks over the Capacity & Fleet Management APIs:

- ``GovernanceMetricsCheck`` (CAP01-01): the governance API exposes the
  Delivered, Healthy, Reserved, and Active capacity metrics for nodes and GPUs.
- ``FleetManagementApiCheck`` (CAP02-01): the resource governance API returns a
  complete per-node record (identity, health, allocation, hardware, region).
- ``ResourceDiscoveryApiCheck`` (CAP03-01): newly delivered capacity is
  discoverable from a pollable index that gives each resource a stable
  identifier.

All three only inspect provider-neutral JSON produced by a step script, so any
provider that emits the documented fields can reuse them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from isvtest.core.validation import BaseValidation

# Metric buckets the governance API must expose, in the conventional ordering
# (Delivered ⊇ Reserved ⊇ Active; Healthy is independent of allocation state).
REQUIRED_METRICS: tuple[str, ...] = ("delivered", "healthy", "reserved", "active")

# Resource dimensions surfaced per metric.
REQUIRED_RESOURCES: tuple[str, ...] = ("nodes", "gpus")

# CAP02 fields that identify the node and the hardware behind it. Every node
# record carries these regardless of whether the node is allocated.
FLEET_IDENTITY_FIELDS: tuple[str, ...] = ("node_id", "hardware_type", "account_id", "region")

# CAP02 fields that only exist while a node is allocated to a workload, so they
# are required exactly when the record reports ``in_use``. Demanding them
# unconditionally would fail an idle fleet; ignoring them would let an API that
# never reports allocation pass.
FLEET_ALLOCATION_FIELDS: tuple[str, ...] = ("instance_id", "project_id")

# The Healthy/Unhealthy classification CAP02 requires. A node the API did not
# classify (reported as "unknown" or omitted) does not satisfy the requirement.
FLEET_HEALTH_STATES: frozenset[str] = frozenset({"healthy", "unhealthy"})

# Every CAP02 field, in the order the requirement lists them.
FLEET_NODE_FIELDS: tuple[str, ...] = (
    "node_id",
    "health_state",
    "instance_id",
    "created_at",
    "hardware_type",
    "gpu_count",
    "account_id",
    "project_id",
    "in_use",
    "region",
)


class GovernanceMetricsCheck(BaseValidation):
    """Validate the governance API returns the required capacity metrics.

    Asserts that the step output exposes per-resource counts (nodes, GPUs) for
    the four governance metric buckets (Delivered, Healthy, Reserved, Active)
    and that the relationships between them are internally consistent.

    Config:
        step_output: Step output containing the governance metrics.
        min_delivered_nodes: Optional minimum Delivered node count (default: 0).
        min_delivered_gpus: Optional minimum Delivered GPU count (default: 0).

    Step output:
        success: bool
        platform: str
        metrics: dict[str, dict[str, int]]:
            delivered: {"nodes": int, "gpus": int}
            healthy:   {"nodes": int, "gpus": int}
            reserved:  {"nodes": int, "gpus": int}
            active:    {"nodes": int, "gpus": int}

    Definitions (provider-agnostic):
        Delivered: hardware the provider has onboarded and made available to
            tenants (any reservable/active state).
        Healthy:   subset of Delivered passing the provider's health probes.
        Reserved:  subset of Delivered allocated to a tenant (in-use or held).
        Active:    subset of Reserved currently running tenant workloads.
    """

    description: ClassVar[str] = "Check governance API exposes Delivered/Healthy/Reserved/Active node and GPU metrics"
    timeout: ClassVar[int] = 60

    def run(self) -> None:
        """Validate metric presence, value sanity, and inter-metric relationships."""
        step_output = self.config.get("step_output", {})

        if not step_output.get("success"):
            self.set_failed(f"Governance metrics step failed: {step_output.get('error', 'Unknown error')}")
            return

        metrics = step_output.get("metrics")
        if not isinstance(metrics, dict):
            self.set_failed("Governance step output is missing the 'metrics' object")
            return

        missing_metrics = [m for m in REQUIRED_METRICS if m not in metrics]
        if missing_metrics:
            self.set_failed(f"Governance metrics missing required buckets: {', '.join(missing_metrics)}")
            return

        # Validate the shape and values of every bucket up front; bail out
        # before relationship checks if anything is malformed (so we report
        # the schema problem rather than a misleading consistency error).
        bucket_values: dict[str, dict[str, int]] = {}
        for metric_name in REQUIRED_METRICS:
            bucket = metrics[metric_name]
            if not isinstance(bucket, dict):
                self.set_failed(f"Governance metric '{metric_name}' is not an object")
                return

            resources: dict[str, int] = {}
            for resource in REQUIRED_RESOURCES:
                if resource not in bucket:
                    self.set_failed(f"Governance metric '{metric_name}' is missing required resource '{resource}'")
                    return
                value = bucket[resource]
                # bool is a subclass of int in Python; reject it explicitly so a
                # truthy/falsy flag is not silently accepted as a count.
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    self.set_failed(
                        f"Governance metric '{metric_name}.{resource}' must be a non-negative integer, got {value!r}"
                    )
                    return
                resources[resource] = value
            bucket_values[metric_name] = resources
            self.report_subtest(
                f"metric_{metric_name}",
                passed=True,
                message=f"{metric_name}: nodes={resources['nodes']}, gpus={resources['gpus']}",
            )

        min_nodes = self._coerce_non_negative_int("min_delivered_nodes", default=0)
        min_gpus = self._coerce_non_negative_int("min_delivered_gpus", default=0)
        if min_nodes is None or min_gpus is None:
            return

        delivered_nodes = bucket_values["delivered"]["nodes"]
        delivered_gpus = bucket_values["delivered"]["gpus"]

        threshold_failures: list[str] = []
        if delivered_nodes < min_nodes:
            threshold_failures.append(f"Delivered nodes {delivered_nodes} < min {min_nodes}")
        if delivered_gpus < min_gpus:
            threshold_failures.append(f"Delivered gpus {delivered_gpus} < min {min_gpus}")

        # Inter-metric ordering: Delivered ⊇ Reserved ⊇ Active and Delivered ⊇ Healthy.
        relationship_failures = self._check_relationships(bucket_values)

        failures = threshold_failures + relationship_failures
        if failures:
            self.set_failed(f"Governance metrics invariants violated: {'; '.join(failures)}")
            return

        self.set_passed(f"Governance metrics OK (delivered: nodes={delivered_nodes}, gpus={delivered_gpus})")

    def _coerce_non_negative_int(self, key: str, *, default: int) -> int | None:
        """Read ``key`` from config and coerce to int >= 0; fail otherwise."""
        raw = self.config.get(key, default)
        if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
            self.set_failed(f"`{key}` must be a non-negative integer, got {raw!r}")
            return None
        return raw

    def _check_relationships(self, buckets: dict[str, dict[str, int]]) -> list[str]:
        """Return a list of human-readable invariant violations (empty if OK)."""
        # subset pairs: (subset_metric, superset_metric)
        invariants: tuple[tuple[str, str], ...] = (
            ("healthy", "delivered"),
            ("reserved", "delivered"),
            ("active", "reserved"),
        )
        failures: list[str] = []
        for subset, superset in invariants:
            for resource in REQUIRED_RESOURCES:
                sub = buckets[subset][resource]
                sup = buckets[superset][resource]
                if sub > sup:
                    failures.append(f"{subset} {resource} ({sub}) exceeds {superset} {resource} ({sup})")
        return failures


def _text(record: Any, field: str) -> str:
    """Return a record's field as a stripped string, or '' when absent/not text."""
    if not isinstance(record, dict):
        return ""
    value = record.get(field)
    return value.strip() if isinstance(value, str) else ""


def _is_iso_timestamp(value: str) -> bool:
    """Return whether ``value`` parses as an ISO 8601 / RFC 3339 timestamp."""
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _duplicate_ids(records: list[Any], field: str) -> list[str]:
    """Return the identifiers reported more than once by ``records``, sorted."""
    seen: set[str] = set()
    duplicates: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        identifier = _text(record, field)
        if not identifier:
            continue
        if identifier in seen:
            duplicates.add(identifier)
        seen.add(identifier)
    return sorted(duplicates)


class FleetManagementApiCheck(BaseValidation):
    """Validate the fleet management API returns a complete record per node.

    CAP02 enumerates the information the resource governance API must return
    for every node. This check asserts each node record carries all of it, with
    the right shape: identity and hardware fields are always required, the
    allocation fields (``instance_id``, ``project_id``) are required exactly
    when the record reports the node is in use, ``health_state`` must be an
    actual Healthy/Unhealthy classification, and ``node_id`` must be unique
    across the fleet.

    Config:
        step_output: Step output containing the per-node fleet inventory.
        min_nodes: Minimum number of node records expected (default: 1).

    Step output:
        success: bool
        platform: str
        nodes_checked: int
        nodes: list[dict]:
            node_id: str -- unique identifier for the node
            health_state: str -- "healthy" | "unhealthy"
            instance_id: str -- identifier for the workload on the node
            created_at: str -- ISO 8601 creation timestamp
            hardware_type: str -- hardware model descriptor
            gpu_count: int -- GPUs on the node
            account_id: str -- top-level organization/account identifier
            project_id: str -- nested project/sub-account identifier
            in_use: bool -- whether the node is turned on and in use
            region: str -- region of the data center hosting the node
    """

    description: ClassVar[str] = "Check fleet management API returns the required record for every node"
    timeout: ClassVar[int] = 120

    def run(self) -> None:
        """Validate per-node field completeness, typing, and node-ID uniqueness."""
        step_output = self.config.get("step_output", {})

        if not step_output.get("success"):
            self.set_failed(f"Fleet inventory step failed: {step_output.get('error', 'Unknown error')}")
            return

        nodes = step_output.get("nodes")
        if not isinstance(nodes, list):
            self.set_failed("Fleet inventory step output is missing the 'nodes' list")
            return

        min_nodes = self._parse_positive_int("min_nodes", default=1)
        if min_nodes is None:
            return

        if len(nodes) < min_nodes:
            self.set_failed(f"Expected at least {min_nodes} node record(s), got {len(nodes)}")
            return

        failed: dict[str, str] = {}
        for index, node in enumerate(nodes):
            label = _text(node, "node_id") or f"node[{index}]"
            problems = self._node_problems(node)
            self.report_subtest(
                f"node_{label}",
                passed=not problems,
                message=(
                    f"Node {label}: {'; '.join(problems)}"
                    if problems
                    else f"Node {label}: all {len(FLEET_NODE_FIELDS)} required fields reported"
                ),
            )
            if problems:
                failed[label] = problems[0]

        duplicates = _duplicate_ids(nodes, "node_id")
        if duplicates:
            self.set_failed(f"Fleet inventory reports duplicate node_id(s): {', '.join(duplicates)}")
            return

        if failed:
            detail = ", ".join(f"{label} ({reason})" for label, reason in failed.items())
            self.set_failed(f"Fleet inventory incomplete for {len(failed)}/{len(nodes)} node(s): {detail}")
            return

        self.set_passed(f"Fleet management API returns the required record for all {len(nodes)} node(s)")

    def _node_problems(self, node: Any) -> list[str]:
        """Return the human-readable field problems for one node record."""
        if not isinstance(node, dict):
            return ["record is not an object"]

        problems = [f"missing {field}" for field in FLEET_IDENTITY_FIELDS if not _text(node, field)]

        health_state = _text(node, "health_state").lower()
        if health_state not in FLEET_HEALTH_STATES:
            problems.append(f"health_state {health_state or 'missing'!r} is not a Healthy/Unhealthy classification")

        created_at = _text(node, "created_at")
        if not created_at:
            problems.append("missing created_at")
        elif not _is_iso_timestamp(created_at):
            problems.append(f"created_at {created_at!r} is not an ISO 8601 timestamp")

        gpu_count = node.get("gpu_count")
        if isinstance(gpu_count, bool) or not isinstance(gpu_count, int) or gpu_count < 0:
            problems.append(f"gpu_count must be a non-negative integer, got {gpu_count!r}")

        in_use = node.get("in_use")
        if not isinstance(in_use, bool):
            problems.append(f"in_use must be a boolean, got {in_use!r}")
        elif in_use:
            problems.extend(
                f"missing {field} while in use" for field in FLEET_ALLOCATION_FIELDS if not _text(node, field)
            )

        return problems


class ResourceDiscoveryApiCheck(BaseValidation):
    """Validate newly delivered capacity is discoverable from a stable index.

    CAP03 rules out capacity being handed over by phone, Slack, or email: the
    provider must expose a "Resource Index" that can be polled and gives each
    resource a stable identifier. This check asserts the index was polled more
    than once (so stability is observed rather than asserted), that no
    identifier changed or disappeared between the first and last poll, that
    every entry carries a unique, non-empty identifier, and that at least one
    indexed resource has actually been discovered -- an index whose capacity was
    never ingested does not show that delivered capacity is discoverable.

    ``delivery_reason`` is reported but not asserted. The plan item requires a
    stable identifier; the reason a resource is being delivered is useful
    context that no provider API is known to expose as a dedicated field, so
    gating on it would fail providers that meet the requirement as written.

    Config:
        step_output: Step output containing the polled resource index.
        min_resources: Minimum number of indexed resources expected (default: 1).
        min_polls: Minimum number of polls the step must have made (default: 2).

    Step output:
        success: bool
        platform: str
        polls: int -- how many times the index was polled
        poll_interval_seconds: int -- delay between polls
        identifiers_stable: bool -- no identifier changed across the polls
        unstable_identifiers: list[str] -- identifiers seen in the first poll
            but missing from the last (capacity appearing mid-run is expected
            and is not instability)
        resources_discovered: int
        resources: list[dict]:
            resource_id: str -- stable identifier for the delivered resource
            discovered: bool -- whether the resource has been ingested yet
            delivery_reason: str -- why the capacity is being provided, when the
                index states one; reported only, never asserted
    """

    description: ClassVar[str] = "Check newly delivered capacity is discoverable with stable resource identifiers"
    timeout: ClassVar[int] = 300

    def run(self) -> None:
        """Validate poll coverage, identifier stability, and per-resource fields."""
        step_output = self.config.get("step_output", {})

        if not step_output.get("success"):
            self.set_failed(f"Resource discovery step failed: {step_output.get('error', 'Unknown error')}")
            return

        resources = step_output.get("resources")
        if not isinstance(resources, list):
            self.set_failed("Resource discovery step output is missing the 'resources' list")
            return

        min_resources = self._parse_positive_int("min_resources", default=1)
        min_polls = self._parse_positive_int("min_polls", default=2)
        if min_resources is None or min_polls is None:
            return

        if len(resources) < min_resources:
            self.set_failed(f"Expected at least {min_resources} indexed resource(s), got {len(resources)}")
            return

        polls = step_output.get("polls")
        if isinstance(polls, bool) or not isinstance(polls, int) or polls < min_polls:
            self.set_failed(f"Resource index must be polled at least {min_polls} time(s), got {polls!r}")
            return
        self.report_subtest(
            "index_pollable",
            passed=True,
            message=f"Resource index polled {polls} time(s) every {step_output.get('poll_interval_seconds', '?')}s",
        )

        unstable = [str(i) for i in (step_output.get("unstable_identifiers") or [])]
        stable = bool(step_output.get("identifiers_stable")) and not unstable
        self.report_subtest(
            "identifiers_stable",
            passed=stable,
            message=(
                f"{len(unstable)} identifier(s) changed across polls: {', '.join(unstable)}"
                if not stable
                else f"All {len(resources)} resource identifier(s) unchanged across {polls} poll(s)"
            ),
        )

        incomplete = self._incomplete_resources(resources)
        duplicates = _duplicate_ids(resources, "resource_id")

        # "Discoverable" means the delivered capacity was actually ingested, not
        # merely listed: an index of entries that never resolved to a resource
        # would otherwise satisfy every other assertion here.
        discovered = [r for r in resources if isinstance(r, dict) and r.get("discovered") is True]
        self.report_subtest(
            "capacity_discovered",
            passed=bool(discovered),
            message=(
                f"{len(discovered)}/{len(resources)} indexed resource(s) discovered"
                if discovered
                else f"None of the {len(resources)} indexed resource(s) have been discovered"
            ),
        )

        failures: list[str] = []
        if not stable:
            failures.append("resource identifiers are not stable across polls")
        if duplicates:
            failures.append(f"duplicate resource_id(s): {', '.join(duplicates)}")
        if incomplete:
            detail = ", ".join(f"{label} ({reason})" for label, reason in incomplete.items())
            failures.append(f"{len(incomplete)}/{len(resources)} entr(ies) incomplete: {detail}")
        if not discovered:
            failures.append(f"none of the {len(resources)} indexed resource(s) have been discovered")

        if failures:
            self.set_failed(f"Resource discovery API does not meet the index contract: {'; '.join(failures)}")
            return

        self.set_passed(
            f"Resource index exposes {len(resources)} resource(s) with stable identifiers across {polls} poll(s), "
            f"{len(discovered)} discovered"
        )

    def _incomplete_resources(self, resources: list[Any]) -> dict[str, str]:
        """Return ``label -> reason`` for index entries with no stable identifier.

        Also reports a subtest per entry, noting the delivery reason when the
        index states one. An unstated reason is recorded as context, not a gap.
        """
        incomplete: dict[str, str] = {}
        for index, resource in enumerate(resources):
            if not isinstance(resource, dict):
                incomplete[f"resource[{index}]"] = "entry is not an object"
                self.report_subtest(f"resource[{index}]", passed=False, message="Index entry is not an object")
                continue
            identifier = _text(resource, "resource_id")
            label = identifier or f"resource[{index}]"
            reason = _text(resource, "delivery_reason")
            self.report_subtest(
                f"resource_{label}",
                passed=bool(identifier),
                message=(
                    f"Resource {label}: missing resource_id"
                    if not identifier
                    else f"Resource {label}: delivered for {reason}"
                    if reason
                    else f"Resource {label}: identified, no delivery reason stated"
                ),
            )
            if not identifier:
                incomplete[label] = "missing resource_id"
        return incomplete
