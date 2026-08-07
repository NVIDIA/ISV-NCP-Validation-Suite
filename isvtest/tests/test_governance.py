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

"""Tests for governance and capacity-fleet API validations."""

from __future__ import annotations

import copy
from typing import Any

from isvtest.validations.governance import (
    FleetManagementApiCheck,
    GovernanceMetricsCheck,
    ResourceDiscoveryApiCheck,
)


def _metrics_output(
    *,
    success: bool = True,
    delivered: dict[str, int] | None = None,
    healthy: dict[str, int] | None = None,
    reserved: dict[str, int] | None = None,
    active: dict[str, int] | None = None,
    error: str = "",
) -> dict[str, Any]:
    """Build a governance metrics step output with valid defaults.

    Defaults satisfy the inter-metric invariants (Healthy/Reserved ⊆ Delivered,
    Active ⊆ Reserved) so individual fields can be overridden per test.
    """
    return {
        "success": success,
        "platform": "nico",
        "site_id": "test-site-001",
        "machine_count": 20,
        "metrics": {
            "delivered": delivered or {"nodes": 20, "gpus": 160},
            "healthy": healthy or {"nodes": 19, "gpus": 152},
            "reserved": reserved or {"nodes": 15, "gpus": 120},
            "active": active or {"nodes": 10, "gpus": 80},
        },
        "error": error,
    }


class TestGovernanceMetricsCheck:
    """Tests for GovernanceMetricsCheck."""

    def test_well_formed_metrics_pass(self) -> None:
        """All four buckets present with consistent counts -- should pass."""
        check = GovernanceMetricsCheck(config={"step_output": _metrics_output()})
        check.run()
        assert check._passed is True
        # One passing subtest per bucket, so callers see the counts.
        bucket_subtests = [r for r in check._subtest_results if r["name"].startswith("metric_")]
        assert {r["name"] for r in bucket_subtests} == {
            "metric_delivered",
            "metric_healthy",
            "metric_reserved",
            "metric_active",
        }
        assert all(r["passed"] for r in bucket_subtests)
        assert "delivered" in check._output

    def test_step_failure_propagates(self) -> None:
        """When the underlying step reports failure the check should fail."""
        check = GovernanceMetricsCheck(config={"step_output": _metrics_output(success=False, error="API down")})
        check.run()
        assert check._passed is False
        assert "API down" in check._error

    def test_missing_metrics_object_fails(self) -> None:
        """A step output without a 'metrics' object should fail with a clear message."""
        output = _metrics_output()
        del output["metrics"]
        check = GovernanceMetricsCheck(config={"step_output": output})
        check.run()
        assert check._passed is False
        assert "missing the 'metrics' object" in check._error

    def test_missing_required_bucket_fails(self) -> None:
        """All four canonical buckets are required."""
        output = _metrics_output()
        del output["metrics"]["active"]
        check = GovernanceMetricsCheck(config={"step_output": output})
        check.run()
        assert check._passed is False
        assert "missing required buckets" in check._error
        assert "active" in check._error

    def test_missing_resource_field_fails(self) -> None:
        """Each bucket must expose both ``nodes`` and ``gpus``."""
        output = _metrics_output()
        del output["metrics"]["delivered"]["gpus"]
        check = GovernanceMetricsCheck(config={"step_output": output})
        check.run()
        assert check._passed is False
        assert "delivered" in check._error and "gpus" in check._error

    def test_negative_count_fails(self) -> None:
        """Counts must be non-negative integers."""
        output = _metrics_output(delivered={"nodes": -1, "gpus": 0})
        check = GovernanceMetricsCheck(config={"step_output": output})
        check.run()
        assert check._passed is False
        assert "delivered.nodes" in check._error

    def test_bool_rejected_as_count(self) -> None:
        """A boolean masquerading as an int should be rejected."""
        output = _metrics_output()
        output["metrics"]["healthy"]["nodes"] = True  # type: ignore[assignment]
        check = GovernanceMetricsCheck(config={"step_output": output})
        check.run()
        assert check._passed is False
        assert "healthy.nodes" in check._error

    def test_string_value_fails(self) -> None:
        """Non-integer count types should be rejected."""
        output = _metrics_output()
        output["metrics"]["reserved"]["gpus"] = "120"  # type: ignore[assignment]
        check = GovernanceMetricsCheck(config={"step_output": output})
        check.run()
        assert check._passed is False
        assert "reserved.gpus" in check._error

    def test_healthy_exceeds_delivered_fails(self) -> None:
        """Healthy must be a subset of Delivered."""
        output = _metrics_output(
            delivered={"nodes": 5, "gpus": 40},
            healthy={"nodes": 6, "gpus": 40},
        )
        check = GovernanceMetricsCheck(config={"step_output": output})
        check.run()
        assert check._passed is False
        assert "healthy nodes" in check._error
        assert "delivered nodes" in check._error

    def test_reserved_exceeds_delivered_fails(self) -> None:
        """Reserved must be a subset of Delivered."""
        output = _metrics_output(
            delivered={"nodes": 5, "gpus": 40},
            reserved={"nodes": 5, "gpus": 48},
        )
        check = GovernanceMetricsCheck(config={"step_output": output})
        check.run()
        assert check._passed is False
        assert "reserved gpus" in check._error

    def test_active_exceeds_reserved_fails(self) -> None:
        """Active must be a subset of Reserved."""
        output = _metrics_output(
            reserved={"nodes": 3, "gpus": 24},
            active={"nodes": 4, "gpus": 24},
        )
        check = GovernanceMetricsCheck(config={"step_output": output})
        check.run()
        assert check._passed is False
        assert "active nodes" in check._error
        assert "reserved nodes" in check._error

    def test_min_delivered_thresholds_enforced(self) -> None:
        """Configurable minimum thresholds enforce a delivered fleet floor."""
        output = _metrics_output(delivered={"nodes": 0, "gpus": 0})
        check = GovernanceMetricsCheck(config={"step_output": output, "min_delivered_nodes": 1})
        check.run()
        assert check._passed is False
        assert "Delivered nodes 0" in check._error

    def test_min_delivered_thresholds_default_zero(self) -> None:
        """Without overrides, a zero-machine site is still well-formed."""
        zero = {"nodes": 0, "gpus": 0}
        output = _metrics_output(delivered=zero, healthy=zero, reserved=zero, active=zero)
        check = GovernanceMetricsCheck(config={"step_output": output})
        check.run()
        assert check._passed is True

    def test_invalid_min_threshold_type_fails(self) -> None:
        """A non-int min threshold should produce an actionable error."""
        check = GovernanceMetricsCheck(
            config={
                "step_output": _metrics_output(),
                "min_delivered_nodes": "many",
            }
        )
        check.run()
        assert check._passed is False
        assert "min_delivered_nodes" in check._error

    def test_bucket_not_an_object_fails(self) -> None:
        """A metric bucket that is not a dict should be rejected up front."""
        output = _metrics_output()
        output["metrics"]["healthy"] = [1, 2, 3]  # type: ignore[assignment]
        check = GovernanceMetricsCheck(config={"step_output": output})
        check.run()
        assert check._passed is False
        assert "healthy" in check._error

    def test_empty_step_output_fails(self) -> None:
        """Empty step_output should fail (no success flag)."""
        check = GovernanceMetricsCheck(config={"step_output": {}})
        check.run()
        assert check._passed is False
        assert "step failed" in check._error

    def test_default_step_output_unchanged(self) -> None:
        """The helper should hand back independent dicts so tests don't bleed into each other."""
        # If the default mutates across calls a later test could silently see
        # the previous test's overrides; pin the contract here.
        first = _metrics_output()
        second = _metrics_output()
        assert first is not second
        assert first["metrics"] == second["metrics"]
        # Mutating one must not change the other.
        snapshot = copy.deepcopy(second["metrics"])
        first["metrics"]["delivered"]["nodes"] = 42
        assert second["metrics"] == snapshot


def _node(**overrides: Any) -> dict[str, Any]:
    """Build a complete CAP02 node record; override individual fields per test."""
    node = {
        "node_id": "node-1",
        "health_state": "healthy",
        "instance_id": "instance-1",
        "created_at": "2026-01-02T03:04:05Z",
        "hardware_type": "dgx-gb300",
        "gpu_count": 8,
        "account_id": "test-org",
        "project_id": "project-1",
        "in_use": True,
        "region": "us-west-1",
    }
    node.update(overrides)
    return node


def _fleet_output(
    *, success: bool = True, nodes: list[dict[str, Any]] | None = None, error: str = ""
) -> dict[str, Any]:
    """Build a fleet inventory step output with one complete node by default."""
    records = [_node()] if nodes is None else nodes
    return {
        "success": success,
        "platform": "nico",
        "site_id": "test-site-001",
        "nodes_checked": len(records),
        "nodes": records,
        "error": error,
    }


class TestFleetManagementApiCheck:
    """Tests for FleetManagementApiCheck (CAP02-01)."""

    def test_complete_records_pass(self) -> None:
        """A fleet whose records carry every required field should pass."""
        check = FleetManagementApiCheck(config={"step_output": _fleet_output()})
        check.run()
        assert check._passed is True, check._error
        assert [r["name"] for r in check._subtest_results] == ["node_node-1"]

    def test_step_failure_propagates(self) -> None:
        """When the underlying step reports failure the check should fail."""
        check = FleetManagementApiCheck(config={"step_output": _fleet_output(success=False, error="API down")})
        check.run()
        assert check._passed is False
        assert "API down" in check._error

    def test_missing_nodes_list_fails(self) -> None:
        """A step output without a 'nodes' list should fail with a clear message."""
        output = _fleet_output()
        del output["nodes"]
        check = FleetManagementApiCheck(config={"step_output": output})
        check.run()
        assert check._passed is False
        assert "missing the 'nodes' list" in check._error

    def test_min_nodes_enforced(self) -> None:
        """An empty fleet should not satisfy the configured node floor."""
        check = FleetManagementApiCheck(config={"step_output": _fleet_output(nodes=[])})
        check.run()
        assert check._passed is False
        assert "at least 1 node record" in check._error

    def test_missing_identity_field_fails(self) -> None:
        """Identity fields are required regardless of allocation state."""
        check = FleetManagementApiCheck(config={"step_output": _fleet_output(nodes=[_node(region="")])})
        check.run()
        assert check._passed is False
        assert "missing region" in check._error

    def test_unclassified_health_state_fails(self) -> None:
        """A node the API never classified does not satisfy the health requirement."""
        check = FleetManagementApiCheck(config={"step_output": _fleet_output(nodes=[_node(health_state="unknown")])})
        check.run()
        assert check._passed is False
        assert "Healthy/Unhealthy classification" in check._error

    def test_non_iso_created_at_fails(self) -> None:
        """The creation timestamp must actually be a timestamp."""
        check = FleetManagementApiCheck(config={"step_output": _fleet_output(nodes=[_node(created_at="last week")])})
        check.run()
        assert check._passed is False
        assert "not an ISO 8601 timestamp" in check._error

    def test_zero_gpu_count_is_allowed(self) -> None:
        """A CPU-only node reports zero GPUs, which is a valid count."""
        check = FleetManagementApiCheck(config={"step_output": _fleet_output(nodes=[_node(gpu_count=0)])})
        check.run()
        assert check._passed is True, check._error

    def test_bool_rejected_as_gpu_count(self) -> None:
        """A boolean masquerading as a GPU count should be rejected."""
        check = FleetManagementApiCheck(config={"step_output": _fleet_output(nodes=[_node(gpu_count=True)])})
        check.run()
        assert check._passed is False
        assert "gpu_count" in check._error

    def test_in_use_must_be_boolean(self) -> None:
        """``In Use`` is a True/False status, not a string."""
        check = FleetManagementApiCheck(config={"step_output": _fleet_output(nodes=[_node(in_use="yes")])})
        check.run()
        assert check._passed is False
        assert "in_use must be a boolean" in check._error

    def test_idle_node_may_omit_allocation_fields(self) -> None:
        """A node that is not in use has no workload or project to report."""
        idle = _node(in_use=False, instance_id="", project_id="")
        check = FleetManagementApiCheck(config={"step_output": _fleet_output(nodes=[idle])})
        check.run()
        assert check._passed is True, check._error

    def test_in_use_node_must_report_allocation_fields(self) -> None:
        """A node reported as in use must name the workload running on it."""
        check = FleetManagementApiCheck(config={"step_output": _fleet_output(nodes=[_node(instance_id="")])})
        check.run()
        assert check._passed is False
        assert "missing instance_id while in use" in check._error

    def test_duplicate_node_ids_fail(self) -> None:
        """Node IDs identify a node, so the fleet must not repeat one."""
        output = _fleet_output(nodes=[_node(), _node()])
        check = FleetManagementApiCheck(config={"step_output": output})
        check.run()
        assert check._passed is False
        assert "duplicate node_id(s): node-1" in check._error

    def test_all_failing_nodes_are_reported(self) -> None:
        """Every bad record gets a subtest, so one summary names the whole gap."""
        nodes = [_node(node_id="a", region=""), _node(node_id="b", hardware_type=""), _node(node_id="c")]
        check = FleetManagementApiCheck(config={"step_output": _fleet_output(nodes=nodes)})
        check.run()
        assert check._passed is False
        assert "2/3 node(s)" in check._error
        assert [r["passed"] for r in check._subtest_results] == [False, False, True]


def _resource(**overrides: Any) -> dict[str, Any]:
    """Build a complete CAP03 index entry; override individual fields per test."""
    resource = {
        "resource_id": "expected-machine-1",
        "delivery_reason": "capacity fulfillment on gb300 project",
        "discovered": True,
    }
    resource.update(overrides)
    return resource


def _discovery_output(
    *,
    success: bool = True,
    polls: int = 2,
    unstable_identifiers: list[str] | None = None,
    resources: list[dict[str, Any]] | None = None,
    error: str = "",
) -> dict[str, Any]:
    """Build a resource discovery step output with one stable entry by default."""
    entries = [_resource()] if resources is None else resources
    return {
        "success": success,
        "platform": "nico",
        "site_id": "test-site-001",
        "polls": polls,
        "poll_interval_seconds": 5,
        "unstable_identifiers": unstable_identifiers or [],
        "resources_checked": len(entries),
        "resources": entries,
        "error": error,
    }


class TestResourceDiscoveryApiCheck:
    """Tests for ResourceDiscoveryApiCheck (CAP03-01)."""

    def test_stable_index_passes(self) -> None:
        """A polled index with stable identifiers and stated reasons should pass."""
        check = ResourceDiscoveryApiCheck(config={"step_output": _discovery_output()})
        check.run()
        assert check._passed is True, check._error
        assert {r["name"] for r in check._subtest_results} == {
            "index_pollable",
            "identifiers_stable",
            "capacity_discovered",
            "resource_expected-machine-1",
        }

    def test_step_failure_propagates(self) -> None:
        """When the underlying step reports failure the check should fail."""
        check = ResourceDiscoveryApiCheck(config={"step_output": _discovery_output(success=False, error="API down")})
        check.run()
        assert check._passed is False
        assert "API down" in check._error

    def test_missing_resources_list_fails(self) -> None:
        """A step output without a 'resources' list should fail with a clear message."""
        output = _discovery_output()
        del output["resources"]
        check = ResourceDiscoveryApiCheck(config={"step_output": output})
        check.run()
        assert check._passed is False
        assert "missing the 'resources' list" in check._error

    def test_single_poll_cannot_prove_stability(self) -> None:
        """One poll observes nothing about stability, so it must not pass."""
        check = ResourceDiscoveryApiCheck(config={"step_output": _discovery_output(polls=1)})
        check.run()
        assert check._passed is False
        assert "polled at least 2 time(s)" in check._error

    def test_changed_identifier_fails(self) -> None:
        """An identifier that disappears between polls is not stable."""
        output = _discovery_output(unstable_identifiers=["expected-machine-9"])
        check = ResourceDiscoveryApiCheck(config={"step_output": output})
        check.run()
        assert check._passed is False
        assert "not stable across polls" in check._error

    def test_missing_delivery_reason_is_reported_not_fatal(self) -> None:
        """An unstated reason is context; the plan item requires the identifier."""
        output = _discovery_output(resources=[_resource(delivery_reason="")])
        check = ResourceDiscoveryApiCheck(config={"step_output": output})
        check.run()
        assert check._passed is True, check._error
        reported = next(r for r in check._subtest_results if r["name"] == "resource_expected-machine-1")
        assert reported["passed"] is True
        assert "no delivery reason stated" in reported["message"]

    def test_missing_resource_id_fails(self) -> None:
        """An entry with no identifier cannot be tracked across polls."""
        output = _discovery_output(resources=[_resource(resource_id="")])
        check = ResourceDiscoveryApiCheck(config={"step_output": output})
        check.run()
        assert check._passed is False
        assert "missing resource_id" in check._error

    def test_duplicate_resource_ids_fail(self) -> None:
        """A stable identifier must identify exactly one delivered resource."""
        output = _discovery_output(resources=[_resource(), _resource()])
        check = ResourceDiscoveryApiCheck(config={"step_output": output})
        check.run()
        assert check._passed is False
        assert "duplicate resource_id(s): expected-machine-1" in check._error

    def test_min_resources_enforced(self) -> None:
        """An empty index does not demonstrate discoverable capacity."""
        check = ResourceDiscoveryApiCheck(config={"step_output": _discovery_output(resources=[])})
        check.run()
        assert check._passed is False
        assert "at least 1 indexed resource" in check._error

    def test_an_index_that_emptied_mid_run_names_the_vanished_identifiers(self) -> None:
        """An emptied index trips the resource floor, but drift is the real cause.

        Reporting only the count would read as though the site never had any
        capacity, rather than that it lost what it had between polls.
        """
        output = _discovery_output(resources=[], unstable_identifiers=["expected-machine-1"])
        check = ResourceDiscoveryApiCheck(config={"step_output": output})
        check.run()
        assert check._passed is False
        assert "got 0" in check._error
        assert "1 identifier(s) vanished across polls: expected-machine-1" in check._error

    def test_index_of_undiscovered_capacity_fails(self) -> None:
        """Listing capacity that was never ingested does not make it discoverable."""
        output = _discovery_output(resources=[_resource(discovered=False)])
        check = ResourceDiscoveryApiCheck(config={"step_output": output})
        check.run()
        assert check._passed is False
        assert "have been discovered" in check._error

    def test_one_discovered_entry_is_enough(self) -> None:
        """Capacity still awaiting ingestion rides along with what has arrived."""
        output = _discovery_output(
            resources=[_resource(), _resource(resource_id="expected-machine-2", discovered=False)]
        )
        check = ResourceDiscoveryApiCheck(config={"step_output": output})
        check.run()
        assert check._passed is True, check._error
        reported = next(r for r in check._subtest_results if r["name"] == "capacity_discovered")
        assert "1/2" in reported["message"]
