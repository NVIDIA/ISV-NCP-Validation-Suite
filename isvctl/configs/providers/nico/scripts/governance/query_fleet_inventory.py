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

"""Report the per-node fleet management record for a NICo site (CAP02-01).

CAP02 requires the resource governance API to return a fixed set of information
for every node. This script reads the NICo machine list plus the site record and
maps them onto that provider-neutral contract:

  Node ID            <- machine.id
  Health State       <- health.alerts (empty -> healthy, non-empty -> unhealthy);
                        a machine with no health report at all is reported as
                        "unknown" so an unclassified node is not silently passed
  Instance ID        <- machine.instanceId
  Creation Timestamp <- machine.created, else the earliest statusHistory entry
  Hardware Type      <- machine.hwSkuDeviceType, else productName
  GPU Count          <- machineCapabilities entries of type GPU
  Account/ID         <- site.org, the NGC organization the site belongs to. Read
                        from the site record rather than echoed back from --org,
                        which would assert nothing about what the API reports.
  Project/ID         <- machine.tenantId
  In Use             <- machine.status == "InUse"
  Region             <- the site's location (city/state/country). NICo exposes no
                        region field, and a site is a single data center, so its
                        location is the region it sits in. Left empty when the
                        site has no location, so CAP02 reports the gap instead of
                        passing on a stand-in such as the site name.

NICo API endpoints used:
  GET /v2/org/{org}/carbide/machine?siteId={site_id}
  GET /v2/org/{org}/carbide/site/{site_id}

Auth:
  - NICO_BEARER_TOKEN, or
  - OIDC client_credentials via NICO_SSA_ISSUER,
    NICO_CLIENT_ID, NICO_CLIENT_SECRET, and optional NICO_OIDC_SCOPE.

Required JSON output fields:
  {
    "success": true,
    "platform": "nico",
    "site_id": "...",
    "nodes_checked": 1,
    "nodes": [
      {
        "node_id": "...",
        "health_state": "healthy",
        "instance_id": "...",
        "created_at": "2026-01-02T03:04:05Z",
        "hardware_type": "dgx-gb300",
        "gpu_count": 8,
        "account_id": "ncx",
        "project_id": "...",
        "in_use": true,
        "region": "Santa Clara, CA, US"
      }
    ]
  }

A site with no ingested machines emits a structured skip (``skipped`` /
``skip_reason``) so a site with no hardware discovered yet is not a hard failure.

Usage:
    NICO_BEARER_TOKEN=<token> python query_fleet_inventory.py \
        --org <org> --site-id <uuid> --api-base <url>

    Wired via the bare_metal suite:
      uv run isvctl test run -f isvctl/configs/providers/nico/config/bare_metal.yaml

Reference:
    NVIDIA/infra-controller: rest-api/api/pkg/api/model/machine.go (APIMachine),
    rest-api/api/pkg/api/model/site.go (APISite, APISiteLocation)
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Allow importing from sibling common/ directory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.inventory import first_string
from common.nico_client import NicoAuthError, forge_get, forge_get_all, resolve_auth, sum_capabilities

# Machine status that means the node is powered on and running a tenant workload.
IN_USE_STATUS = "InUse"

# Machine fields carrying the hardware model descriptor, in priority order.
HARDWARE_TYPE_KEYS = ("hwSkuDeviceType", "productName")

# APISiteLocation fields, coarsest last, joined to name the region a site sits in.
SITE_LOCATION_KEYS = ("city", "state", "country")


def site_region(site: dict[str, Any]) -> str:
    """Return the region a site's nodes are deployed in, or '' when unstated.

    NICo has no region field; a site carries a structured location instead, and
    a site is a single data center. Returning '' for a site with no location
    lets CAP02 report the missing region rather than pass on the site's name,
    which identifies the site but says nothing about where it is.
    """
    location = site.get("location")
    if not isinstance(location, dict):
        return ""
    parts = [first_string(location, key) for key in SITE_LOCATION_KEYS]
    return ", ".join(part for part in parts if part)


def health_state(machine: dict[str, Any]) -> str:
    """Classify a machine as healthy/unhealthy, or unknown when unreported.

    NICo reports health as an alert-driven document: no alerts means healthy.
    A machine carrying no probe data and no observation timestamp has not been
    classified at all, which is distinct from being healthy.
    """
    health = machine.get("health") or {}
    if not (health.get("successes") or health.get("alerts") or health.get("observedAt")):
        return "unknown"
    return "unhealthy" if health.get("alerts") else "healthy"


def created_at(machine: dict[str, Any]) -> str:
    """Return the machine's creation timestamp.

    Falls back to the earliest ``statusHistory`` entry, which records when NICo
    first observed the machine in a lifecycle state. ISO 8601 timestamps sort
    lexicographically, so ``min`` picks the earliest.
    """
    explicit = first_string(machine, "created")
    if explicit:
        return explicit

    stamps = [
        first_string(entry, "created", "updated")
        for entry in (machine.get("statusHistory") or [])
        if isinstance(entry, dict)
    ]
    stamps = [s for s in stamps if s]
    return min(stamps) if stamps else ""


def node_record(machine: dict[str, Any], *, account_id: str, region: str) -> dict[str, Any]:
    """Build the provider-neutral CAP02 fleet record for one NICo machine."""
    return {
        "node_id": machine.get("id", ""),
        "health_state": health_state(machine),
        "instance_id": first_string(machine, "instanceId"),
        "created_at": created_at(machine),
        "hardware_type": first_string(machine, *HARDWARE_TYPE_KEYS),
        "gpu_count": sum_capabilities(machine.get("machineCapabilities") or [], "GPU"),
        "account_id": account_id,
        "project_id": first_string(machine, "tenantId"),
        "in_use": machine.get("status") == IN_USE_STATUS,
        "region": region,
    }


def main() -> int:
    """Query the NICo fleet and print the per-node governance records as JSON."""
    parser = argparse.ArgumentParser(description="Report the NICo fleet management inventory")
    parser.add_argument("--org", required=True, help="NGC org name")
    parser.add_argument("--site-id", required=True, help="NICo site UUID")
    parser.add_argument("--api-base", required=True, help="NICo API base URL")
    args = parser.parse_args()

    result: dict[str, Any] = {
        "success": False,
        "platform": "nico",
        "site_id": args.site_id,
        "nodes_checked": 0,
        "nodes": [],
    }

    try:
        auth = resolve_auth()

        machines = forge_get_all(
            args.org,
            "machine",
            auth.token,
            base_url=args.api_base,
            params={"siteId": args.site_id},
            result_key="machines",
        )

        if not machines:
            result["success"] = True
            result["skipped"] = True
            result["skip_reason"] = "No machines found at site; no fleet records to report"
            print(json.dumps(result, indent=2))
            return 0

        site = forge_get(args.org, f"site/{args.site_id}", auth.token, base_url=args.api_base)
        region = site_region(site)
        account_id = first_string(site, "org")

        result["nodes"] = [node_record(m, account_id=account_id, region=region) for m in machines]
        result["nodes_checked"] = len(result["nodes"])
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
