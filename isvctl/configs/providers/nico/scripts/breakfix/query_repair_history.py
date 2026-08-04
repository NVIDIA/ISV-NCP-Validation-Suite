#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Query repair history for NICo machines (BFX02-03).

Derives repair/maintenance history from ``statusHistory`` and repair-related
machine labels (for example ``RepairStatus``). NICo repair integration docs:
infra-controller/docs/manuals/repair/overview.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from breakfix._common import emit, history_entries, list_site_machines, machine_labels

_REPAIR_STATUSES = {"Maintenance", "Reset", "Error", "Repairing"}


def _repair_entries(machine: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    labels = machine_labels(machine)
    repair_status = labels.get("RepairStatus") or labels.get("repair_status")
    if repair_status:
        entries.append(
            {
                "status": repair_status,
                "message": "machine label",
                "updated_at": None,
                "action": repair_status,
                "source": "label",
            }
        )
    for item in history_entries(machine):
        status = str(item.get("status") or "")
        if status not in _REPAIR_STATUSES and status != "InUse":
            continue
        entries.append(
            {
                "status": status,
                "message": item.get("message") or "",
                "updated_at": item.get("timestamp") or item.get("updatedAt"),
                "action": item.get("message") or status,
                "source": "statusHistory",
            }
        )
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description="Query NICo repair history")
    parser.add_argument("--org", required=True)
    parser.add_argument("--site-id", required=True)
    parser.add_argument("--api-base", required=True)
    args = parser.parse_args()

    machines, result = list_site_machines(org=args.org, site_id=args.site_id, api_base=args.api_base)
    if result.get("skipped"):
        result["history_queryable"] = False
        result["records"] = []
        return emit(result)
    if not result.get("success"):
        return emit(result)

    records: list[dict[str, Any]] = []
    for machine in machines:
        entries = _repair_entries(machine)
        if not entries:
            continue
        records.append({"machine_id": machine.get("id", ""), "entries": entries})

    result["history_queryable"] = True
    result["records"] = records
    return emit(result)


if __name__ == "__main__":
    sys.exit(main())
