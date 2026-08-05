#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Query maintenance events for a NICo site (BFX02-01).

Maps NICo machine ``Maintenance`` status and ``maintenanceMessage`` fields into
provider-neutral maintenance event records. NICo does not expose a dedicated
break-fix events API; this read-only step documents observability via the
machine REST resource.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from breakfix._common import emit, history_entries, list_site_machines


def _opened_at(machine: dict[str, Any]) -> str | None:
    """Return the timestamp of the machine's most recent Maintenance transition."""
    for entry in reversed(history_entries(machine)):
        status = str(entry.get("status") or "").strip()
        if status == "Maintenance":
            return entry.get("timestamp") or entry.get("updatedAt")
    return None


def main() -> int:
    """Map NICo machine maintenance state into neutral event records as JSON."""
    parser = argparse.ArgumentParser(description="Query NICo maintenance events")
    parser.add_argument("--org", required=True)
    parser.add_argument("--site-id", required=True)
    parser.add_argument("--api-base", required=True)
    args = parser.parse_args()

    machines, result = list_site_machines(org=args.org, site_id=args.site_id, api_base=args.api_base)
    if result.get("skipped"):
        result["events_queryable"] = False
        result["events"] = []
        return emit(result)
    if not result.get("success"):
        return emit(result)

    events: list[dict[str, Any]] = []
    for machine in machines:
        status = str(machine.get("status") or "")
        message = machine.get("maintenanceMessage")
        if status != "Maintenance" and not message:
            continue
        machine_id = machine.get("id", "")
        events.append(
            {
                "machine_id": machine_id,
                "hardware_id": machine_id,
                "status": status.lower() if status else "maintenance",
                "message": message or "",
                "opened_at": _opened_at(machine),
            }
        )

    result["events_queryable"] = True
    result["events"] = events
    return emit(result)


if __name__ == "__main__":
    sys.exit(main())
