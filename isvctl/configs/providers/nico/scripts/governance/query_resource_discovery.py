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
index is for and is reported separately as new.

The delivery reason is read from the record itself -- a well-known label or a
free-text field. It is deliberately not inferred from lifecycle state: an
inferred reason would let the check pass without the API ever stating why the
capacity is being provided, which is the assertion CAP03 actually makes.

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
    "identifiers_stable": true,
    "unstable_identifiers": [],
    "new_identifiers": [],
    "resources_discovered": 1,
    "resources": [
      {
        "resource_id": "...",
        "resource_type": "machine",
        "delivery_reason": "capacity fulfillment on gb300 project",
        "delivery_reason_source": "label:DeliveryReason",
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
    OpenAPI spec: rest-api/openapi/spec.yaml (ExpectedMachine schema)
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

# Expected-machine label keys carrying the delivery reason, in priority order.
DELIVERY_REASON_LABEL_KEYS = ("DeliveryReason", "deliveryReason", "delivery_reason", "reason")

# Expected-machine top-level fields carrying the delivery reason, in priority order.
DELIVERY_REASON_FIELD_KEYS = ("deliveryReason", "reason", "description", "notes")


def delivery_reason(record: dict[str, Any]) -> tuple[str, str]:
    """Return ``(reason, source)`` for an index entry, or ``("", "")`` if unstated."""
    labels = record.get("labels")
    if isinstance(labels, dict):
        for key in DELIVERY_REASON_LABEL_KEYS:
            reason = first_string(labels, key)
            if reason:
                return reason, f"label:{key}"

    for key in DELIVERY_REASON_FIELD_KEYS:
        reason = first_string(record, key)
        if reason:
            return reason, f"field:{key}"

    return "", ""


def resource_record(record: dict[str, Any]) -> dict[str, Any]:
    """Build the provider-neutral CAP03 index entry for one expected machine."""
    reason, source = delivery_reason(record)
    return {
        "resource_id": first_string(record, "id"),
        "resource_type": "machine",
        "delivery_reason": reason,
        "delivery_reason_source": source,
        "discovered": bool(first_string(record, "machineId")),
    }


def poll_index(
    org: str,
    token: str,
    *,
    site_id: str,
    api_base: str,
) -> list[dict[str, Any]]:
    """Fetch one full page-through of the expected-machine resource index."""
    return forge_get_all(
        org,
        "expected-machine",
        token,
        base_url=api_base,
        params={"siteId": site_id},
        result_key="expectedMachines",
    )


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
        "identifiers_stable": False,
        "unstable_identifiers": [],
        "new_identifiers": [],
        "resources_discovered": 0,
        "resources": [],
    }

    try:
        auth = resolve_auth()

        polls: list[list[dict[str, Any]]] = []
        for attempt in range(max(1, args.polls)):
            if attempt:
                time.sleep(max(0, args.poll_interval))
            polls.append(poll_index(args.org, auth.token, site_id=args.site_id, api_base=args.api_base))
            result["polls"] = len(polls)

        if not any(polls):
            result["success"] = True
            result["skipped"] = True
            result["skip_reason"] = "Resource index is empty at this site; no delivered capacity to report"
            print(json.dumps(result, indent=2))
            return 0

        first_ids = {first_string(r, "id") for r in polls[0] if first_string(r, "id")}
        last_ids = {first_string(r, "id") for r in polls[-1] if first_string(r, "id")}

        result["unstable_identifiers"] = sorted(first_ids - last_ids)
        result["new_identifiers"] = sorted(last_ids - first_ids)
        result["identifiers_stable"] = not result["unstable_identifiers"]
        result["resources"] = [resource_record(r) for r in polls[-1]]
        result["resources_discovered"] = len(result["resources"])
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
