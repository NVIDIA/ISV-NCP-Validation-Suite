#!/usr/bin/env python3
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

"""Report a GPU fault through the NICo repair API and observe the repair state (BFX01-01).

BFX01-01 asks for a GPU reset "via the break-fix API". NICo exposes no GPU-reset
operation -- and neither does the automation behind it, which discovers repair
work by polling and then runs for minutes to weeks. What a tenant *can* do
synchronously is report a GPU fault and watch the provider move the node into a
repair state. That is what this step exercises.

The mechanism is NICo's *online repair*: a privileged tenant reports a
``healthIssue`` against a machine, NICo applies a site health override and moves
the assigned instance from ``Ready`` to ``Repairing``, and clearing online repair
takes it back out again. The instance keeps its tenant assignment throughout, so
the round trip is non-destructive and reversible -- unlike the disruptive
release-for-repair path (``DELETE instance`` with ``machineHealthIssue``), which
belongs to BFX01-02.

Online repair requires a machine with an assigned instance in ``Ready``. A site
with no such machine emits a structured skip rather than a failure: nothing is
broken, the precondition simply is not met. The same applies to a site whose
machines report no GPUs, since a GPU fault report would be meaningless there.

NICo API endpoints used (the ``/carbide/`` segment is the current deployed name
for what newer docs call ``/nico/``; the other NICo scripts use it too):
  GET   /{org}/carbide/machine?siteId={site_id}
  GET   /{org}/carbide/instance/{instance_id}
  PATCH /{org}/carbide/machine/{machine_id}   (operationId update-machine)

Auth:
  - NICO_BEARER_TOKEN, or OIDC client_credentials
    (NICO_SSA_ISSUER / NICO_CLIENT_ID / NICO_CLIENT_SECRET).
  - Requires provider admin, or a tenant admin whose tenant has the
    ``TargetedInstanceCreation`` capability. NICo rejects anyone else with 403.

Entering online repair requires acknowledging data-corruption and repair-team-access
risk; those acknowledgements are NICo's required contract, not a choice this step
makes. ``allowAutoInstanceDeletionOnFailure`` is pinned ``false`` so NICo never
deletes the tenant's instance on our behalf.

Online repair is cleared in a ``finally``, so the node cannot be left in
``Repairing`` even when the teardown phase never runs. A failure to clear it fails
the step (via ``cleanup_errors``) because a node stuck out of the allocatable pool
must be visible. ``--skip-restore`` leaves it in repair for debugging; recover with
``PATCH machine`` ``{"onlineRepair": {"enabled": false}}``, or by removing the
health override at ``DELETE /machine/{id}/health-report/{source}``.

Required JSON output fields:
  {
    "success": true,
    "platform": "nico",
    "site_id": "...",
    "operation": {
      "requested": true,             // API accepted the GPU fault report
      "repair_state_observed": true, // provider moved the node into repair
      "restored": true,              // provider took it back out afterwards
      "node_id": "fm100...",
      "message": "..."               // diagnostic detail
    }
  }

Usage:
    NICO_BEARER_TOKEN=<token> \
        python request_gpu_repair.py --org <org> --site-id <uuid> --api-base <url>

    Wired via the bare_metal suite:
      uv run isvctl test run -f isvctl/configs/providers/nico/config/bare_metal.yaml

Reference:
    infra-controller docs/manuals/repair/online_repair.md
    infra-controller rest-api/openapi/spec.yaml (update-machine, MachineUpdateRequest)
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Any

# Allow importing from sibling common/ directory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from breakfix._common import emit, list_site_machines
from common.nico_client import (
    NicoAuthError,
    forge_get,
    forge_patch,
    resolve_auth,
    sum_capabilities,
)

REPAIR_STATUS = "Repairing"
READY_STATUS = "Ready"

POLL_INTERVAL_SECONDS = 5
POLL_DEADLINE_SECONDS = 180

# NICo requires a healthIssue when entering online repair. Category must be one of
# Hardware, Network, Performance, Storage, Software, Other.
GPU_HEALTH_ISSUE: dict[str, str] = {
    "category": "Hardware",
    "summary": "Validation suite GPU fault report (BFX01-01)",
    "details": (
        "Reported by the NVIDIA AI Cloud Validation Suite to verify that a tenant-reported GPU "
        "fault moves the node into a provider repair state. No physical fault is implied and no "
        "repair action is expected; online repair is cleared again immediately."
    ),
}


def _enter_body() -> dict[str, Any]:
    """Build the update-machine body that enters online repair."""
    return {
        "onlineRepair": {
            "enabled": True,
            # Pinned false: NICo must never delete the tenant's instance on our behalf.
            "policy": {"allowAutoInstanceDeletionOnFailure": False},
            "acknowledgments": {
                "acceptDataCorruptionRisk": True,
                "acceptRepairTeamAccess": True,
                "acceptInstanceDeletionRisk": True,
            },
        },
        "healthIssue": dict(GPU_HEALTH_ISSUE),
    }


def _exit_body() -> dict[str, Any]:
    """Build the update-machine body that clears online repair.

    NICo rejects the exit request if it carries healthIssue, policy, or
    acknowledgments, so it must contain nothing but the flag.
    """
    return {"onlineRepair": {"enabled": False}}


def _instance_status(org: str, instance_id: str, token: str, *, base_url: str) -> str:
    """Return an instance's current status, or an empty string when absent."""
    instance = forge_get(org, f"instance/{instance_id}", token, base_url=base_url)
    status = instance.get("status")
    return status if isinstance(status, str) else ""


def _await_status(
    org: str,
    instance_id: str,
    token: str,
    *,
    base_url: str,
    target: str,
    leaving: bool = False,
    deadline_seconds: int = POLL_DEADLINE_SECONDS,
) -> str:
    """Poll an instance until it reaches (or leaves) ``target``; return the last status.

    NICo applies the health override through a site workflow, so the instance
    status changes shortly after the API returns rather than within it.
    """
    deadline = time.monotonic() + deadline_seconds
    status = _instance_status(org, instance_id, token, base_url=base_url)
    while True:
        reached = (status != target) if leaving else (status == target)
        if reached or time.monotonic() >= deadline:
            return status
        time.sleep(POLL_INTERVAL_SECONDS)
        status = _instance_status(org, instance_id, token, base_url=base_url)


def _gpu_machines_with_instances(machines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return machines that have GPUs and an assigned instance."""
    return [
        m
        for m in machines
        if m.get("instanceId") and sum_capabilities(m.get("machineCapabilities") or [], "GPU") > 0
    ]


def _select_target(
    candidates: list[dict[str, Any]], org: str, token: str, *, base_url: str, machine_id: str = ""
) -> tuple[dict[str, Any], str] | None:
    """Return the first (machine, instance_id) whose instance is ``Ready``.

    ``machine_id`` restricts the search to one machine, so an operator can target
    a known node instead of whichever the site happens to offer first.
    """
    for machine in candidates:
        if machine_id and machine.get("id") != machine_id:
            continue
        instance_id = str(machine.get("instanceId") or "")
        if _instance_status(org, instance_id, token, base_url=base_url) == READY_STATUS:
            return machine, instance_id
    return None


def _skip_reason(machines: list[dict[str, Any]], candidates: list[dict[str, Any]], machine_id: str) -> str:
    """Explain why no machine at the site can exercise online repair."""
    if machine_id:
        return (
            f"Machine {machine_id} does not have a GPU and an assigned instance in {READY_STATUS}; "
            "online repair requires both"
        )
    if not candidates:
        return (
            f"None of the {len(machines)} machine(s) at the site has both GPUs and an assigned instance; "
            "online repair requires a GPU node with a tenant instance"
        )
    return (
        f"{len(candidates)} GPU machine(s) have instances but none is in {READY_STATUS}; "
        "online repair requires a Ready instance"
    )


def main() -> int:
    """Report a GPU fault, observe the repair state, and print the JSON contract."""
    parser = argparse.ArgumentParser(description="Report a GPU fault via the NICo online-repair API")
    parser.add_argument("--org", required=True, help="NGC org name")
    parser.add_argument("--site-id", required=True, help="NICo site UUID")
    parser.add_argument("--api-base", required=True, help="NICo API base URL")
    parser.add_argument("--machine-id", default="", help="Target a specific machine instead of the first eligible one")
    parser.add_argument(
        "--skip-restore",
        action="store_true",
        help="Leave the node in online repair for debugging (it is cleared by default)",
    )
    args = parser.parse_args()

    empty_contract = {"operation": {"requested": False, "repair_state_observed": False, "restored": False}}
    machines, result = list_site_machines(
        org=args.org, site_id=args.site_id, api_base=args.api_base, empty_contract=empty_contract
    )
    if not machines:
        return emit(result)

    operation: dict[str, Any] = {"requested": False, "repair_state_observed": False, "restored": False}
    result["operation"] = operation

    auth = None
    entered = False
    instance_id = ""

    try:
        auth = resolve_auth()
        candidates = _gpu_machines_with_instances(machines)
        target = _select_target(candidates, args.org, auth.token, base_url=args.api_base, machine_id=args.machine_id)

        if target is None:
            result["skipped"] = True
            result["skip_reason"] = _skip_reason(machines, candidates, args.machine_id)
            return emit(result)

        machine, instance_id = target
        machine_id = str(machine.get("id") or "")
        operation["node_id"] = machine_id

        forge_patch(args.org, f"machine/{machine_id}", auth.token, base_url=args.api_base, body=_enter_body())
        entered = True
        operation["requested"] = True

        status = _await_status(
            args.org, instance_id, auth.token, base_url=args.api_base, target=REPAIR_STATUS
        )
        operation["repair_state_observed"] = status == REPAIR_STATUS
        if not operation["repair_state_observed"]:
            operation["message"] = (
                f"Online repair was accepted but the instance stayed in {status or 'an unknown state'} "
                f"rather than {REPAIR_STATUS} within {POLL_DEADLINE_SECONDS}s"
            )

    except NicoAuthError as e:
        result["success"] = False
        result["error_type"] = "auth"
        result["error"] = str(e)
    except Exception as e:
        result["success"] = False
        result["error"] = f"{type(e).__name__}: {e}"
    finally:
        # Clear online repair in the process that entered it, so the node cannot be
        # left out of the allocatable pool even when teardown never executes.
        if entered and auth is not None and not args.skip_restore:
            try:
                forge_patch(
                    args.org,
                    f"machine/{operation['node_id']}",
                    auth.token,
                    base_url=args.api_base,
                    body=_exit_body(),
                )
                status = _await_status(
                    args.org, instance_id, auth.token, base_url=args.api_base, target=REPAIR_STATUS, leaving=True
                )
                operation["restored"] = status != REPAIR_STATUS
                if not operation["restored"]:
                    raise RuntimeError(f"instance stayed in {REPAIR_STATUS} after clearing online repair")
            except Exception as e:
                # A node stranded in repair must fail the step even when the report itself worked.
                result["cleanup_errors"] = [f"{type(e).__name__}: {e}"]
                result["success"] = False
                result["error"] = f"Failed to clear online repair: {e}"
        elif entered and args.skip_restore:
            result["cleanup_skipped"] = True

    return emit(result)


if __name__ == "__main__":
    sys.exit(main())
