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

"""Return a node to the provider for maintenance (BFX01-02).

BFX01-02 is the destructive half of the break-fix lifecycle: the tenant is
relinquishing the node -- "drain my jobs, I am done with it" -- rather than
flagging that it will need attention while keeping it. Reporting a node and
keeping it is BFX01-06 (``report_node_repair.py``).

The mechanism is NICo's *release for repair*: ``DELETE instance`` carrying a
``machineHealthIssue``. One call does both halves, and the pairing is the point.
A bare delete hands the machine straight back to the allocatable pool, where the
next tenant inherits whatever was wrong with it; the health issue is what
quarantines it for repair instead. So the check asserts both: the instance is
gone *and* the machine did not silently return to service.

**This is irreversible.** The instance and everything on it are destroyed, and
nothing in this script can undo that -- unlike BFX01-06, which clears online
repair in a ``finally``. Two independent confirmations are therefore required
and neither is sufficient alone:

  1. ``--instance-id <uuid>``, naming the exact instance -- supplied by the
     provider config from ``NICO_INSTANCE_ID``. There is deliberately no
     discovery: a run cannot select a victim, so a misconfigured site cannot
     cost someone their work. Shared lab sites routinely carry exactly one
     tenant instance and it is usually not ours.
  2. ``NICO_ALLOW_RELEASE_FOR_REPAIR=1``, a separate deliberate act.

Two independent environment variables, so neither a stray instance id left over
from another step nor a blanket opt-in in a CI runner can arm this on its own.

Without both, the step reports what it would delete and stops, which makes a
plain run a dry run.

NICo API endpoints used (the ``/carbide/`` segment is the current deployed name
for what newer docs call ``/nico/``; the other NICo scripts use it too):
  GET    /{org}/carbide/instance/{instance_id}
  GET    /{org}/carbide/machine/{machine_id}
  DELETE /{org}/carbide/instance/{instance_id}   (operationId delete-instance)

Auth:
  - NICO_BEARER_TOKEN, or OIDC client_credentials
    (NICO_SSA_ISSUER / NICO_CLIENT_ID / NICO_CLIENT_SECRET).
  - Requires the tenant that owns the instance, or provider admin.

The JSON contract is ``operation.{requested, accepted, instance_deleted,
machine_quarantined, instance_id, machine_id, message}``, documented alongside
the other break-fix steps in ``isvctl/configs/suites/README.md`` and asserted by
``ReturnNodeMaintenanceCheck``.

Usage:
    NICO_BEARER_TOKEN=<token> NICO_ALLOW_RELEASE_FOR_REPAIR=1 \
        python return_node_maintenance.py --org <org> --site-id <uuid> \
            --api-base <url> --instance-id <uuid>

Reference:
    infra-controller docs/manuals/repair/release_instance_for_repair.md
    infra-controller rest-api/openapi/spec.yaml (delete-instance)
"""

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

# Allow importing from sibling common/ directory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from breakfix._common import emit
from common.inventory import first_string
from common.nico_client import (
    NicoAuth,
    NicoAuthError,
    forge_delete,
    forge_get,
    resolve_auth,
)

READY_STATUS = "Ready"

# Machine states that mean "not handed back to the next tenant". NICo moves a
# released machine out of the allocatable pool while the repair flags stand;
# the exact label varies by build, so match the set rather than one string.
QUARANTINED_STATUSES = frozenset({"Repairing", "Error", "Maintenance", "Quarantined", "Unavailable"})

# The second of the two confirmations. Naming an instance is the first; this is
# a separate deliberate act, so neither a stray env var in a CI runner nor a
# copied command line can destroy an instance on its own.
ALLOW_ENV = "NICO_ALLOW_RELEASE_FOR_REPAIR"

POLL_INTERVAL_SECONDS = 5
# The delete returns as soon as NICo accepts it; the machine leaves the pool
# through a site workflow that may queue behind other work.
POLL_DEADLINE_SECONDS = 300

# NICo requires a health issue alongside the delete. Category must be one of
# Hardware, Network, Performance, Storage, Software, Other.
RETURN_HEALTH_ISSUE: dict[str, str] = {
    "category": "Hardware",
    "summary": "Validation suite node return for maintenance (BFX01-02)",
    "details": (
        "Reported by the NVIDIA AI Cloud Validation Suite to verify that a tenant can return a node "
        "to the provider for maintenance. The instance was relinquished deliberately as part of the "
        "test; the machine should be quarantined for repair rather than returned to the pool."
    ),
}


def _delete_body() -> dict[str, Any]:
    """Build the delete-instance body that quarantines the machine for repair."""
    return {"machineHealthIssue": dict(RETURN_HEALTH_ISSUE)}


def _instance(org: str, instance_id: str, token: str, *, base_url: str) -> dict[str, Any]:
    """Fetch one instance, or an empty dict when it is genuinely gone.

    Only a 404 counts as gone. Every other failure propagates, because "absent"
    is load-bearing twice over here: before the delete it means there is nothing
    to return, and after it means the return worked. Letting a 401 or a 5xx
    answer either question would turn a provider outage into a clean skip, or
    into a false report that the instance was destroyed.
    """
    try:
        return forge_get(org, f"instance/{instance_id}", token, base_url=base_url)
    except HTTPError as e:
        if e.code == 404:
            return {}
        raise


def _machine_status(org: str, machine_id: str, token: str, *, base_url: str) -> str:
    """Return a machine's current status.

    Errors propagate for the same reason as ``_instance``: an unreadable machine
    is not evidence that it stayed in service, and reporting it as such would
    blame the provider for a fault on our side.
    """
    return first_string(forge_get(org, f"machine/{machine_id}", token, base_url=base_url), "status")


def _await_deletion(org: str, instance_id: str, token: str, *, base_url: str) -> bool:
    """Poll until the instance is gone; return whether it went away."""
    deadline = time.monotonic() + POLL_DEADLINE_SECONDS
    while True:
        if not _instance(org, instance_id, token, base_url=base_url):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(POLL_INTERVAL_SECONDS)


def _await_quarantine(org: str, machine_id: str, token: str, *, base_url: str) -> tuple[bool, str]:
    """Poll until the machine leaves service; return ``(quarantined, last status)``.

    ``Ready`` is the failure case worth naming: it means the provider took the
    node back and immediately offered it to someone else, which is precisely
    what the health issue was supposed to prevent.
    """
    deadline = time.monotonic() + POLL_DEADLINE_SECONDS
    status = ""
    while True:
        status = _machine_status(org, machine_id, token, base_url=base_url)
        if status in QUARANTINED_STATUSES:
            return True, status
        if time.monotonic() >= deadline:
            return False, status
        time.sleep(POLL_INTERVAL_SECONDS)


def _confirmations(instance_id: str) -> str:
    """Return why the run is not allowed to delete, or an empty string when it is."""
    if not instance_id:
        return (
            "No instance named. This step deletes a tenant instance and cannot undo it, so it "
            "never discovers a target; name the instance you intend to destroy with --instance-id "
            f"<uuid> (NICO_INSTANCE_ID via the provider config), and set {ALLOW_ENV}=1"
        )
    if os.environ.get(ALLOW_ENV) != "1":
        return (
            f"Would delete instance {instance_id} and return its machine for repair, but "
            f"{ALLOW_ENV} is not set. Naming the instance is only the first of two confirmations "
            "required for an irreversible delete"
        )
    return ""


def main() -> int:
    """Return a node for maintenance and print the JSON contract."""
    parser = argparse.ArgumentParser(description="Return a node to the provider for maintenance (NICo)")
    parser.add_argument("--org", required=True, help="NGC org name")
    parser.add_argument("--site-id", required=True, help="NICo site UUID")
    parser.add_argument("--api-base", required=True, help="NICo API base URL")
    parser.add_argument("--instance-id", default="", help="Instance to relinquish (required to mutate)")
    args = parser.parse_args()

    operation: dict[str, Any] = {
        "requested": False,
        "accepted": False,
        "instance_deleted": False,
        "machine_quarantined": False,
        "instance_id": args.instance_id,
    }
    result: dict[str, Any] = {
        "success": True,
        "platform": "nico",
        "site_id": args.site_id,
        "operation": operation,
    }

    blocked = _confirmations(args.instance_id)
    if blocked:
        # Reported rather than performed, so a plain run is a dry run.
        result["skipped"] = True
        result["skip_reason"] = blocked
        return emit(result)

    auth: NicoAuth | None = None
    try:
        auth = resolve_auth()
        instance = _instance(args.org, args.instance_id, auth.token, base_url=args.api_base)
        if not instance:
            result["skipped"] = True
            result["skip_reason"] = f"Instance {args.instance_id} was not found at the site; nothing to return"
            return emit(result)

        machine_id = first_string(instance, "machineId")
        operation["machine_id"] = machine_id
        if not machine_id:
            result["success"] = False
            result["error"] = (
                f"Instance {args.instance_id} reports no machineId, so the machine's fate after the "
                "delete could not be observed; refusing to destroy it blind"
            )
            return emit(result)

        forge_delete(args.org, f"instance/{args.instance_id}", auth.token, base_url=args.api_base, body=_delete_body())
        operation["requested"] = True
        operation["accepted"] = True

        operation["instance_deleted"] = _await_deletion(args.org, args.instance_id, auth.token, base_url=args.api_base)
        if not operation["instance_deleted"]:
            # A destructive step that cannot confirm its own outcome has not
            # succeeded, whatever the API answered: the instance may or may not
            # be on its way out, and the step must not exit 0 saying otherwise.
            result["success"] = False
            operation["message"] = (
                f"NICo accepted the release but instance {args.instance_id} still existed after "
                f"{POLL_DEADLINE_SECONDS}s"
            )
            result["error"] = operation["message"]
            return emit(result)

        quarantined, status = _await_quarantine(args.org, machine_id, auth.token, base_url=args.api_base)
        operation["machine_quarantined"] = quarantined
        if not quarantined:
            result["success"] = False
            operation["message"] = (
                f"Machine {machine_id} was released with a health issue but reported "
                f"{status or 'an unknown state'} rather than leaving service; a node returned for "
                "maintenance must not go straight back into the allocatable pool"
            )
            result["error"] = operation["message"]

    except NicoAuthError as e:
        result["success"] = False
        result["error_type"] = "auth"
        result["error"] = str(e)
    except Exception as e:
        result["success"] = False
        result["error"] = f"{type(e).__name__}: {e}"

    return emit(result)


if __name__ == "__main__":
    sys.exit(main())
