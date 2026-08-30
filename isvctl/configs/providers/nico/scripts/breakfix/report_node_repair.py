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

"""Report a node to the provider for maintenance and observe the repair state (BFX01-06).

BFX01-06 is the non-destructive half of the break-fix lifecycle: "this node needs
repair eventually, but I am still using it". The tenant keeps the node and its
workload; only the provider's view of the node changes. Relinquishing the node so
the provider can drain and repair it is the destructive counterpart, BFX01-02.

The mechanism is NICo's *online repair*: a privileged tenant reports a
``healthIssue`` against a machine, NICo applies a site health override and moves
the assigned instance from ``Ready`` to ``Repairing``, and clearing online repair
takes it back out again. The instance keeps its tenant assignment throughout, so
the round trip is reversible -- unlike release-for-repair (``DELETE instance``
with ``machineHealthIssue``), which hands the node back.

The report is deliberately node-scoped rather than component-scoped. A tenant may
well be reporting a bad GPU, but NICo manages machines, not GPUs, and its own
online-repair documentation treats a GPU fault as something a tenant *reports*
against the node. So there is one report path for any hardware complaint.

Online repair requires a machine with an assigned instance in ``Ready``. A site
with no such machine emits a structured skip rather than a failure: nothing is
broken, the precondition simply is not met.

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

Mutating requires the operator to opt in. A shared site's only eligible machine may
belong to another tenant, so an auto-discovered target is reported in a structured
skip rather than moved into repair -- which also makes a plain run a dry run. Confirm
with ``--machine-id <id>``, or set ``NICO_ALLOW_ONLINE_REPAIR=1`` to accept whichever
eligible node is found.

Entering online repair requires acknowledging data-corruption and repair-team-access
risk; those acknowledgements are NICo's required contract, not a choice this step
makes. ``allowAutoInstanceDeletionOnFailure`` is pinned ``false`` so NICo never
deletes the tenant's instance on our behalf.

Online repair is cleared in a ``finally``, so the node cannot be left in
``Repairing`` even when the teardown phase never runs. See ``_restore`` for how far
that goes and why -- a node stranded out of the allocatable pool is the worst
outcome this step can produce. The clear runs whenever the enter request *may* have
been applied, not only when NICo confirmed it: a PATCH that timed out on the read
can still have enabled online repair. See ``_enter_may_have_applied``.

``--skip-restore`` leaves the node in repair for debugging; recover with
``PATCH machine`` ``{"onlineRepair": {"enabled": false}}``, or
``DELETE /machine/{id}/health-report/request-online-repair``.

The JSON contract is ``operation.{requested, repair_state_observed, restored,
node_id, message}``, documented alongside the other break-fix steps in
``isvctl/configs/suites/README.md`` and asserted by ``ReportNodeRepairCheck``.

Usage:
    NICO_BEARER_TOKEN=<token> \
        python report_node_repair.py --org <org> --site-id <uuid> --api-base <url>

    Wired via the bare_metal suite:
      uv run isvctl test run -f isvctl/configs/providers/nico/config/bare_metal.yaml

Reference:
    infra-controller docs/manuals/repair/online_repair.md
    infra-controller rest-api/openapi/spec.yaml (update-machine, MachineUpdateRequest)
"""

import argparse
import contextlib
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

# Allow importing from sibling common/ directory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from breakfix._common import emit, list_site_machines
from common.inventory import first_string
from common.nico_client import (
    NicoAuth,
    NicoAuthError,
    delete_if_present,
    forge_get,
    forge_patch,
    resolve_auth,
)

REPAIR_STATUS = "Repairing"
READY_STATUS = "Ready"

# Health override NICo applies while online repair is active. Removing it is the
# fallback when clearing online repair through update-machine does not take effect.
ONLINE_REPAIR_OVERRIDE_SOURCE = "request-online-repair"

# A site's only eligible machine may belong to someone else -- shared lab sites
# routinely carry exactly one tenant instance -- and this step would put it into
# Repairing. So an auto-selected target is reported, not mutated: the operator opts
# in by naming the machine, or by setting this to "1" to accept whatever is found.
# The sibling query_key_access.py mutates by default and opts *out* via
# --no-provision; the difference is blast radius. Minting a throwaway SSH key
# affects nobody, whereas moving a stranger's instance into a repair state does.
AUTO_SELECT_ENV = "NICO_ALLOW_ONLINE_REPAIR"

POLL_INTERVAL_SECONDS = 5
# Generous because NICo applies the override through a site workflow that may queue
# behind other work; a false "never entered repair" is worse than waiting. The worst
# path spends this twice (enter, then clear) plus the shorter fallback below, so the
# step timeout in the provider config must exceed their sum with room for latency.
POLL_DEADLINE_SECONDS = 300
# The override-removal fallback runs only after the primary clear already spent its
# deadline, so it gets a shorter one: it mutates machine state directly instead of
# queueing a site workflow, and the two waits together must fit the step timeout.
FALLBACK_POLL_DEADLINE_SECONDS = 90

# NICo requires a healthIssue when entering online repair. Category must be one of
# Hardware, Network, Performance, Storage, Software, Other.
NODE_HEALTH_ISSUE: dict[str, str] = {
    "category": "Hardware",
    "summary": "Validation suite node repair report (BFX01-06)",
    "details": (
        "Reported by the NVIDIA AI Cloud Validation Suite to verify that a tenant can flag a node "
        "as needing repair and have the provider move it into a repair state. No physical fault is "
        "implied and no repair action is expected; online repair is cleared again immediately."
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
        "healthIssue": dict(NODE_HEALTH_ISSUE),
    }


def _enter_may_have_applied(error: BaseException) -> bool:
    """Return whether a failed enter-repair request may still have taken effect.

    A 4xx means NICo read the request and refused it, so the machine is untouched
    and there is nothing to clear. Anything else leaves it unknown: a read timeout,
    a dropped connection, or a 5xx from a gateway that stopped waiting all happen
    *after* the request reached NICo, which may already have enabled online repair
    and applied the health override. An unknown enter must be followed by a clear,
    because the alternative is a node stranded out of the allocatable pool.
    """
    if isinstance(error, HTTPError):
        return not 400 <= error.code < 500
    return True


def _exit_body() -> dict[str, Any]:
    """Build the update-machine body that clears online repair.

    NICo rejects the exit request if it carries healthIssue, policy, or
    acknowledgments, so it must contain nothing but the flag.
    """
    return {"onlineRepair": {"enabled": False}}


def _instance_status(org: str, instance_id: str, token: str, *, base_url: str) -> str:
    """Return an instance's current status, or an empty string when absent."""
    instance = forge_get(org, f"instance/{instance_id}", token, base_url=base_url)
    return first_string(instance, "status")


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
    while True:
        status = _instance_status(org, instance_id, token, base_url=base_url)
        reached = (status != target) if leaving else (status == target)
        if reached or time.monotonic() >= deadline:
            return status
        time.sleep(POLL_INTERVAL_SECONDS)


def _machines_with_instances(machines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return machines that have an assigned instance."""
    return [m for m in machines if m.get("instanceId")]


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
        return f"Machine {machine_id} does not have an assigned instance in {READY_STATUS}; online repair requires one"
    if not candidates:
        return (
            f"None of the {len(machines)} machine(s) at the site has an assigned instance; "
            "online repair requires a node with a tenant instance"
        )
    return (
        f"{len(candidates)} machine(s) have instances but none is in {READY_STATUS}; "
        "online repair requires a Ready instance"
    )


def _attempt_exit(
    org: str,
    instance_id: str,
    token: str,
    *,
    api_base: str,
    apply: Callable[[], object],
    what: str,
    deadline_seconds: int,
) -> tuple[bool, str]:
    """Run one exit attempt and wait for the node to leave repair.

    ``apply`` performs the mutation -- clearing online repair, or removing the
    health override. Returns ``(left_repair, detail)``, where ``detail`` is empty
    on success and describes the failure otherwise.
    """
    try:
        apply()
        status = _await_status(
            org,
            instance_id,
            token,
            base_url=api_base,
            target=REPAIR_STATUS,
            leaving=True,
            deadline_seconds=deadline_seconds,
        )
        if status != REPAIR_STATUS:
            return True, ""
        return False, f"instance stayed in {REPAIR_STATUS} after {what}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _restore(org: str, machine_id: str, instance_id: str, *, api_base: str, fallback_token: str) -> dict[str, Any]:
    """Take the node back out of repair, and report how much effort that took.

    Returns ``{"restored": bool, "warning": str, "errors": [...]}``. Clearing
    online repair the documented way is tried first; if that leaves the node in
    repair, the health override is removed directly. Only a node still in repair
    after both attempts is an error -- needing the fallback is a provider finding
    worth reporting, but nothing was left behind.
    """
    token = fallback_token
    # Re-mint first: the run can outlive a short-lived access token (NICo SSA
    # tokens last minutes, not hours), and a 401 here would strand the node out of
    # the allocatable pool. If minting fails, the original token is still worth trying.
    with contextlib.suppress(NicoAuthError):
        token = resolve_auth().token

    left_repair, detail = _attempt_exit(
        org,
        instance_id,
        token,
        api_base=api_base,
        apply=lambda: forge_patch(org, f"machine/{machine_id}", token, base_url=api_base, body=_exit_body()),
        what="clearing online repair",
        deadline_seconds=POLL_DEADLINE_SECONDS,
    )
    if left_repair:
        return {"restored": True, "warning": "", "errors": []}

    recovered, fallback_detail = _attempt_exit(
        org,
        instance_id,
        token,
        api_base=api_base,
        apply=lambda: delete_if_present(
            org, f"machine/{machine_id}/health-report/{ONLINE_REPAIR_OVERRIDE_SOURCE}", token, base_url=api_base
        ),
        what=f"removing the {ONLINE_REPAIR_OVERRIDE_SOURCE} override",
        # The override delete mutates state directly rather than queueing a site
        # workflow, so it needs far less room than entering repair did. Keeping the
        # full deadline here would let restore alone consume the whole step timeout
        # and get killed mid-cleanup -- the exact outcome this path exists to prevent.
        deadline_seconds=FALLBACK_POLL_DEADLINE_SECONDS,
    )
    if recovered:
        return {
            "restored": True,
            "warning": f"Clearing online repair did not take effect ({detail}); removed the override directly",
            "errors": [],
        }
    return {"restored": False, "warning": "", "errors": [detail, fallback_detail]}


def main() -> int:
    """Report a node for repair, observe the repair state, and print the JSON contract."""
    parser = argparse.ArgumentParser(description="Report a node for repair via the NICo online-repair API")
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

    operation: dict[str, Any] = {"requested": False, "repair_state_observed": False, "restored": False}

    # Mint the token once and hand it to the listing helper, which would otherwise
    # mint its own. On failure it stays None and the helper re-resolves, so the
    # structured auth-error payload is still built in exactly one place.
    auth: NicoAuth | None = None
    with contextlib.suppress(NicoAuthError):
        auth = resolve_auth()

    machines, result = list_site_machines(
        org=args.org,
        site_id=args.site_id,
        api_base=args.api_base,
        empty_contract={"operation": operation},
        auth=auth,
        # Only id and instanceId are read below.
        include_metadata=False,
    )
    if not machines:
        return emit(result)

    result["operation"] = operation
    instance_id = ""
    # Whether the enter-repair mutation may have landed, which is not the same
    # question as operation["requested"] (NICo answered and confirmed it). A PATCH
    # that timed out after being applied has to be cleared too.
    restore_required = False

    try:
        if auth is None:
            auth = resolve_auth()
        candidates = _machines_with_instances(machines)
        target = _select_target(candidates, args.org, auth.token, base_url=args.api_base, machine_id=args.machine_id)

        if target is None:
            result["skipped"] = True
            result["skip_reason"] = _skip_reason(machines, candidates, args.machine_id)
            return emit(result)

        machine, instance_id = target
        machine_id = str(machine.get("id") or "")
        operation["node_id"] = machine_id

        if not args.machine_id and os.environ.get(AUTO_SELECT_ENV) != "1":
            # Report the target rather than mutating it. This doubles as a dry run:
            # the operator sees exactly which node would enter repair before allowing it.
            result["skipped"] = True
            result["skip_reason"] = (
                f"Would report machine {machine_id} for repair, but an auto-selected node "
                f"is not mutated because it may belong to another tenant. Pass "
                f"--machine-id {machine_id} to confirm this node, or set {AUTO_SELECT_ENV}=1 to "
                f"accept whichever eligible node is found"
            )
            return emit(result)

        try:
            forge_patch(args.org, f"machine/{machine_id}", auth.token, base_url=args.api_base, body=_enter_body())
        except Exception as e:
            restore_required = _enter_may_have_applied(e)
            raise
        restore_required = True
        operation["requested"] = True

        status = _await_status(args.org, instance_id, auth.token, base_url=args.api_base, target=REPAIR_STATUS)
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
        # Take the node back out of repair in the process that put it there, so it
        # cannot be left out of the allocatable pool even when teardown never runs.
        if restore_required:
            if args.skip_restore:
                result["cleanup_skipped"] = True
            else:
                outcome = _restore(
                    args.org,
                    str(operation["node_id"]),
                    instance_id,
                    api_base=args.api_base,
                    fallback_token=auth.token if auth else "",
                )
                operation["restored"] = outcome["restored"]
                if outcome["warning"]:
                    # Carried in operation.message so the bound validation surfaces it;
                    # a provider whose documented exit path did not work is a finding
                    # worth reading even though nothing was left behind.
                    operation["message"] = outcome["warning"]
                if not outcome["restored"]:
                    # A node stranded in repair must fail the step even when the report worked.
                    result["cleanup_errors"] = outcome["errors"]
                    result["success"] = False
                    stranded = f"Node left in {REPAIR_STATUS}: {'; '.join(outcome['errors'])}"
                    # A restore reached from a failed enter already carries the root
                    # cause, and it is usually why the restore failed too, so keep it.
                    prior = result.get("error")
                    result["error"] = f"{prior}; {stranded}" if prior else stranded

    return emit(result)


if __name__ == "__main__":
    sys.exit(main())
