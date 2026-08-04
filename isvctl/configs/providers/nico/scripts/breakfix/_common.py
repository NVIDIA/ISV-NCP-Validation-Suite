# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for NICo break-fix scripts."""

from __future__ import annotations

import json
from typing import Any

from common.nico_client import NicoAuthError, forge_get_all, resolve_auth


def list_site_machines(*, org: str, site_id: str, api_base: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch machines for a site or return a structured failure/skip payload."""
    result: dict[str, Any] = {"success": False, "platform": "nico", "site_id": site_id}
    try:
        auth = resolve_auth()
        machines = forge_get_all(
            org,
            "machine",
            auth.token,
            base_url=api_base,
            params={"siteId": site_id, "includeMetadata": "true"},
            result_key="machines",
        )
    except NicoAuthError as exc:
        result["error"] = str(exc)
        return [], result

    if not machines:
        result.update(
            {
                "success": True,
                "skipped": True,
                "skip_reason": "No machines discovered at the site; break-fix checks require ingested hardware",
            }
        )
        return [], result

    result["success"] = True
    return machines, result


def skip_result(site_id: str, reason: str, *, gap: str = "") -> dict[str, Any]:
    """Build a structured skip payload documenting a known platform gap."""
    payload: dict[str, Any] = {
        "success": True,
        "skipped": True,
        "platform": "nico",
        "site_id": site_id,
        "skip_reason": reason,
    }
    if gap:
        payload["gap"] = gap
    return payload


def emit(result: dict[str, Any]) -> int:
    print(json.dumps(result, indent=2))
    return 0 if result.get("success") else 1


def machine_labels(machine: dict[str, Any]) -> dict[str, str]:
    labels = machine.get("labels") or {}
    if not isinstance(labels, dict):
        return {}
    return {str(k): str(v) for k, v in labels.items() if v is not None}


def history_entries(machine: dict[str, Any]) -> list[dict[str, Any]]:
    history = machine.get("statusHistory") or []
    return [entry for entry in history if isinstance(entry, dict)]
