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
can inspect. Both halves are worth reporting differently:

  - Provider credentials: the firmware versions come back and the check passes.
    That is the "better than nothing" half -- it proves NICo holds the data and
    exposes it, so the remaining work is authorisation rather than plumbing.
  - Tenant credentials: NICo answers 403, and that is *the finding*, not a
    failure of this step. It emits a structured skip naming the gap, so a
    tenant-perspective run reports "not available to a tenant" rather than
    "broken".

A run therefore cannot tell you the tenant half works, only whether the
provider half does. Nothing here escalates privilege to paper over that.

NICo API endpoints used (the ``/carbide/`` segment is the current deployed name
for what newer docs call ``/nico/``; the other NICo scripts use it too):
  GET /{org}/carbide/tray?siteId={site_id}   (operationId get-all-tray)

Field names are read through ``first_string`` against several candidates rather
than one hard-coded spelling: the tray schema is less exercised than
``machine``, and a step that reports "no firmware version" because it looked for
``firmwareVersion`` where the build says ``firmware_version`` would be a false
finding about the provider.

Auth:
  - NICO_BEARER_TOKEN, or OIDC client_credentials
    (NICO_SSA_ISSUER / NICO_CLIENT_ID / NICO_CLIENT_SECRET).
  - Requires provider admin to return data; anything less is the documented gap.

The JSON contract is ``trays[].{tray_id, firmware_version}``, documented
alongside the other break-fix steps in ``isvctl/configs/suites/README.md`` and
asserted by ``NvSwitchFirmwareCheck``.

Usage:
    NICO_BEARER_TOKEN=<token> \
        python query_switch_firmware.py --org <org> --site-id <uuid> --api-base <url>

Reference:
    infra-controller rest-api/openapi/spec.yaml (get-all-tray, Tray)
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

# NICo's tray schema is not as well trodden as machine's, so accept the
# plausible spellings rather than reporting a provider gap that is really ours.
TRAY_ID_KEYS = ("id", "trayId", "tray_id", "name", "hostname")
FIRMWARE_KEYS = ("firmwareVersion", "firmware_version", "firmware")

# get-all-tray is PROVIDER_ADMIN-scoped. A tenant-scoped caller getting 403 is
# the requirement's gap, not a broken step, so it is reported as a skip.
GAP_ID = "BFX03-02"
TENANT_GAP_REASON = (
    "NICo exposes switch tray firmware only to PROVIDER_ADMIN callers (get-all-tray returned 403); "
    "a tenant cannot inspect switch tray firmware, which is the tenant-visible half of BFX03-02"
)


def _tray_record(tray: dict[str, Any]) -> dict[str, str]:
    """Reduce a NICo tray to the two fields the validation reads."""
    return {
        "tray_id": first_string(tray, *TRAY_ID_KEYS),
        "firmware_version": first_string(tray, *FIRMWARE_KEYS),
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
            params={"siteId": args.site_id},
            result_key="trays",
        )
    except NicoAuthError as exc:
        result["error_type"] = "auth"
        result["error"] = str(exc)
        return emit(result)
    except HTTPError as exc:
        if exc.code in (401, 403):
            skip = skip_result(args.site_id, TENANT_GAP_REASON, gap=GAP_ID)
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
            "No switch trays are registered at the site, so tray firmware inspection cannot be demonstrated",
            gap=GAP_ID,
        )
        skip["trays"] = []
        return emit(skip)

    result["success"] = True
    result["trays"] = [_tray_record(tray) for tray in trays if isinstance(tray, dict)]
    return emit(result)


if __name__ == "__main__":
    sys.exit(main())
