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

"""Poll the NICo resource discovery index for delivered capacity (CAP03-01).

CAP03 requires newly delivered capacity to be discoverable from a centralized,
pollable "Resource Index" that gives each resource a stable identifier and says
why it is being provided. In NICo that index is the expected-machine manifest:
each record is registered when capacity is handed over, carries its own stable
``id``, and links to the discovered machine via ``machineId`` once ingested.

This script polls that index more than once so identifier stability is observed
rather than asserted. Identifiers present in the first poll but gone by the last
are reported as unstable; capacity that *appears* mid-run is exactly what the
index is for and is not instability. The script reports only what it observed --
whether that amounts to a stable index is ``ResourceDiscoveryApiCheck``'s call.

The delivery reason is reported when the record states one, and is deliberately
never inferred from lifecycle state -- an inferred reason would read as though
the API had stated why the capacity is being provided when it had not.

NICo has no dedicated delivery-reason field. The only free-text field on an
expected machine is ``description``, and ``labels`` is an operator-controlled
map with no key reserved for a reason. So the reason is best-effort context,
not an API guarantee, and ``ResourceDiscoveryApiCheck`` reports it without
gating on it. The assertion that does hold is the stable identifier: an
expected machine's ``id`` is a server-assigned UUID.

NICo API endpoints used:
  GET /v2/org/{org}/carbide/expected-machine?siteId={site_id}

Auth:
  - NICO_BEARER_TOKEN, or
  - OIDC client_credentials via NICO_SSA_ISSUER,
    NICO_CLIENT_ID, NICO_CLIENT_SECRET, and optional NICO_OIDC_SCOPE.

Required JSON output fields:
  {
    "success": true,
    "platform": "nico",
    "site_id": "...",
    "polls": 2,
    "poll_interval_seconds": 5,
    "unstable_identifiers": [],
    "resources_checked": 1,
    "resources": [
      {
        "resource_id": "...",
        "delivery_reason": "capacity fulfillment on gb300 project",
        "discovered": true
      }
    ]
  }

A site with an empty index emits a structured skip (``skipped`` /
``skip_reason``) so a site with no capacity registered yet is not a hard failure.

Usage:
    NICO_BEARER_TOKEN=<token> python query_resource_discovery.py \
        --org <org> --site-id <uuid> --api-base <url> --polls 2 --poll-interval 5

    Wired via the bare_metal suite:
      uv run isvctl test run -f isvctl/configs/providers/nico/config/bare_metal.yaml

Reference:
    NVIDIA/infra-controller: rest-api/api/pkg/api/model/expectedmachine.go
    (APIExpectedMachine)
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

# Allow importing from sibling common/ directory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.inventory import first_string
from common.nico_client import NicoAuthError, forge_get_all, resolve_auth

# Operator-set label keys that may carry a delivery reason, in priority order.
# NICo reserves no label key for this, so these are a convention a site may
# adopt rather than anything the API guarantees.
DELIVERY_REASON_LABEL_KEYS = ("DeliveryReason", "deliveryReason", "delivery_reason", "reason")


def delivery_reason(record: dict[str, Any]) -> str:
    """Return the stated reason for an index entry, or '' when unstated."""
    labels = record.get("labels")
    if isinstance(labels, dict):
        for key in DELIVERY_REASON_LABEL_KEYS:
            if reason := first_string(labels, key):
                return reason

    return first_string(record, "description")


def identifiers(records: list[dict[str, Any]]) -> set[str]:
    """Return the non-empty resource identifiers in one poll of the index."""
    return {ident for r in records if (ident := first_string(r, "id"))}


def resource_record(record: dict[str, Any]) -> dict[str, Any]:
    """Build the provider-neutral CAP03 index entry for one expected machine."""
    return {
        "resource_id": first_string(record, "id"),
        "delivery_reason": delivery_reason(record),
        "discovered": bool(first_string(record, "machineId")),
    }


def main() -> int:
    """Poll the NICo resource index and print the discovery contract as JSON."""
    parser = argparse.ArgumentParser(description="Poll the NICo resource discovery index")
    parser.add_argument("--org", required=True, help="NGC org name")
    parser.add_argument("--site-id", required=True, help="NICo site UUID")
    parser.add_argument("--api-base", required=True, help="NICo API base URL")
    parser.add_argument("--polls", type=int, default=2, help="How many times to poll the index (default: 2)")
    parser.add_argument("--poll-interval", type=int, default=5, help="Seconds between polls (default: 5)")
    args = parser.parse_args()

    result: dict[str, Any] = {
        "success": False,
        "platform": "nico",
        "site_id": args.site_id,
        "polls": 0,
        "poll_interval_seconds": args.poll_interval,
        "unstable_identifiers": [],
        "resources_checked": 0,
        "resources": [],
    }

    try:
        auth = resolve_auth()

        # Only the first and last poll are compared, so intermediate payloads
        # are reduced to their identifiers rather than retained whole.
        first_ids: set[str] = set()
        latest: list[dict[str, Any]] = []
        indexed_anything = False
        polls = max(1, args.polls)
        for attempt in range(polls):
            if attempt:
                time.sleep(max(0, args.poll_interval))
            latest = forge_get_all(
                args.org,
                "expected-machine",
                auth.token,
                base_url=args.api_base,
                params={"siteId": args.site_id},
                result_key="expectedMachines",
            )
            indexed_anything = indexed_anything or bool(latest)
            if not attempt:
                first_ids = identifiers(latest)
        result["polls"] = polls

        if not indexed_anything:
            result["success"] = True
            result["skipped"] = True
            result["skip_reason"] = "Resource index is empty at this site; no delivered capacity to report"
            print(json.dumps(result, indent=2))
            return 0

        result["unstable_identifiers"] = sorted(first_ids - identifiers(latest))
        result["resources"] = [resource_record(r) for r in latest]
        result["resources_checked"] = len(result["resources"])
        result["success"] = True

    except NicoAuthError as e:
        result["error_type"] = "auth"
        result["error"] = str(e)
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
