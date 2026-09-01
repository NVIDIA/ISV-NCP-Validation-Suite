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

"""Inspect NV switch tray firmware versions through the NICo API (BFX03-02).

NICo models switch trays as a first-class resource carrying a firmware version,
so the inspection is a plain read: list the site's trays and report each one's
version. No BMC, no vendor tooling, no command execution on the hardware.

**BFX03-02 is only half satisfied, and deliberately so.** ``get-all-tray`` is
``PROVIDER_ADMIN``-scoped, while the requirement asks for something a *tenant*
can inspect. Three answers are possible and each means something different:

  - Provider credentials on a Flow site: the firmware versions come back and the
    check passes. That is the "better than nothing" half -- it proves NICo holds
    the data and exposes it, so the remaining work is authorisation rather than
    plumbing.
  - Tenant credentials: NICo answers 403, and that is *the finding*, not a
    failure of this step. A structured skip names the gap, so a
    tenant-perspective run reports "not available to a tenant", not "broken".
  - A site without NICo Flow: NICo answers 412 and there is no tray inventory at
    all. Also a skip, but a different fact -- the capability is absent from the
    site rather than withheld from the caller. Confusing the two would report a
    lab-configuration detail as a provider gap.

A run therefore cannot tell you the tenant half works, only whether the
provider half does. Nothing here escalates privilege to paper over that.

NICo API endpoints used (the ``/carbide/`` segment is the current deployed name
for what newer docs call ``/nico/``; the other NICo scripts use it too):
  GET /{org}/carbide/tray?siteId={site_id}&type=NVSwitch   (operationId get-all-tray)

``type=NVSwitch`` matters: a tray is any rack component, so an unfiltered list
also returns ``Compute`` and ``PowerShelf`` trays. BFX03-02 asks about switch
firmware, and demanding a firmware version from a power shelf would fail the
provider for a question nobody asked.

The response is a bare JSON array of ``Tray``, not a wrapped collection, so no
result key is passed. Identity comes from ``id``, falling back to
``componentId`` then ``name``; the version is ``firmwareVersion``. All are real
fields on the documented schema, and only ``nvLinkDomainId``/``taskStats`` are
marked required there, hence the fallbacks for identity.

Auth:
  - NICO_BEARER_TOKEN, or OIDC client_credentials
    (NICO_SSA_ISSUER / NICO_CLIENT_ID / NICO_CLIENT_SECRET).
  - The spec is explicit: the org must have an Infrastructure Provider entity
    and the caller needs a ``PROVIDER_ADMIN``-suffixed role. Anything less is
    the documented gap, not a fault.

The JSON contract is ``trays[].{tray_id, firmware_version}``, documented
alongside the other break-fix steps in ``isvctl/configs/suites/README.md`` and
asserted by ``NvSwitchFirmwareCheck``.

Usage:
    NICO_BEARER_TOKEN=<token> \
        python query_switch_firmware.py --org <org> --site-id <uuid> --api-base <url>

Reference:
    infra-controller rest-api/openapi/spec.yaml
      - path /v2/org/{org}/nico/tray, operationId get-all-tray
      - components.schemas.Tray
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

# Allow importing from sibling common/ directory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from breakfix._common import emit, skip_result
from common.inventory import first_string
from common.nico_client import NicoAuthError, forge_get_all, resolve_auth

# Tray.id is not in the schema's `required` list, so fall back to the other
# documented identifiers rather than reporting an unidentified tray.
TRAY_ID_KEYS = ("id", "componentId", "name")
FIRMWARE_KEY = "firmwareVersion"

# Tray covers every rack component; only NVSwitch trays are in scope here.
SWITCH_TRAY_TYPE = "NVSwitch"

GAP_ID = "BFX03-02"

# Two different "not available here" answers, worth telling apart because they
# are different findings. Neither is a provider fault, so both skip.
#
# 401/403: get-all-tray is PROVIDER_ADMIN-scoped, so a tenant-scoped caller is
#   turned away. That is exactly the half of BFX03-02 NICo does not satisfy.
TENANT_GAP_REASON = (
    "NICo exposes switch tray firmware only to PROVIDER_ADMIN callers (get-all-tray returned 403); "
    "a tenant cannot inspect switch tray firmware, which is the tenant-visible half of BFX03-02"
)
# 412: trays live in NICo Flow, and a site without Flow has no tray inventory to
#   report at all. Observed on a live v2.2.0 site as
#   {"source":"nico","message":"Site does not have NICo Flow enabled"}. The spec
#   documents this prerequisite and a 412 for the sibling get-all-tasks but not
#   for get-all-tray, so the live build is the authority here.
NO_FLOW_REASON = (
    "The site does not have NICo Flow enabled, so it holds no switch tray inventory to inspect "
    "(get-all-tray returned 412). Tray firmware is a NICo Flow capability; a site without it cannot "
    "demonstrate BFX03-02 either way"
)


def _tray_record(tray: dict[str, Any]) -> dict[str, str]:
    """Reduce a NICo tray to the two fields the validation reads."""
    return {
        "tray_id": first_string(tray, *TRAY_ID_KEYS),
        "firmware_version": first_string(tray, FIRMWARE_KEY),
    }


def main() -> int:
    """Report per-tray firmware versions, or the tenant-visibility gap, as JSON."""
    parser = argparse.ArgumentParser(description="Inspect NV switch tray firmware versions (NICo)")
    parser.add_argument("--org", required=True, help="NGC org name")
    parser.add_argument("--site-id", required=True, help="NICo site UUID")
    parser.add_argument("--api-base", required=True, help="NICo API base URL")
    args = parser.parse_args()

    result: dict[str, Any] = {"success": False, "platform": "nico", "site_id": args.site_id, "trays": []}

    try:
        auth = resolve_auth()
        trays = forge_get_all(
            args.org,
            "tray",
            auth.token,
            base_url=args.api_base,
            params={"siteId": args.site_id, "type": SWITCH_TRAY_TYPE},
        )
    except NicoAuthError as exc:
        result["error_type"] = "auth"
        result["error"] = str(exc)
        return emit(result)
    except HTTPError as exc:
        reason = {401: TENANT_GAP_REASON, 403: TENANT_GAP_REASON, 412: NO_FLOW_REASON}.get(exc.code)
        if reason:
            skip = skip_result(args.site_id, reason, gap=GAP_ID)
            skip["trays"] = []
            return emit(skip)
        result["error"] = f"{type(exc).__name__}: {exc}"
        return emit(result)
    except (URLError, ValueError) as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return emit(result)

    if not trays:
        # A site with no switch trays cannot demonstrate the API either way, so
        # it skips rather than passing on an empty list.
        skip = skip_result(
            args.site_id,
            f"No {SWITCH_TRAY_TYPE} trays are registered at the site, so tray firmware inspection "
            "cannot be demonstrated",
            gap=GAP_ID,
        )
        skip["trays"] = []
        return emit(skip)

    result["success"] = True
    result["trays"] = [_tray_record(tray) for tray in trays if isinstance(tray, dict)]
    return emit(result)


if __name__ == "__main__":
    sys.exit(main())
