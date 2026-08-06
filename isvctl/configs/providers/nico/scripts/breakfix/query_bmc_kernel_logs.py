#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Query BMC kernel logs (BFX03-03) for NICo machines.

Inspects machine health probes for BMC log/sel/kernel signals. NICo aggregates
BMC telemetry into the health report rather than exposing raw kernel log
streams on the tenant REST API.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from breakfix._common import emit, list_site_machines, skip_result
from common.nico_client import probe_text

_LOG_KEYWORDS = ("kernel", "sel", "syslog", "log", "journal")


def _has_kernel_log_signal(health: dict[str, Any]) -> bool:
    """Return whether any BMC log probe is present in a health report."""
    for probe in (health.get("successes") or []) + (health.get("alerts") or []):
        if not isinstance(probe, dict):
            continue
        text = probe_text(probe)
        probe_id = str(probe.get("id") or "").lower()
        if "bmc" not in probe_id and "bmc" not in text:
            continue
        if any(keyword in text for keyword in _LOG_KEYWORDS) or "sel" in probe_id:
            return True
    return False


def main() -> int:
    """Report per-host BMC kernel-log availability from NICo health probes as JSON."""
    parser = argparse.ArgumentParser(description="Query BMC kernel logs (NICo)")
    parser.add_argument("--org", required=True)
    parser.add_argument("--site-id", required=True)
    parser.add_argument("--api-base", required=True)
    args = parser.parse_args()

    machines, result = list_site_machines(
        org=args.org,
        site_id=args.site_id,
        api_base=args.api_base,
        empty_contract={"hosts": []},
    )
    if not machines:
        return emit(result)

    hosts: list[dict[str, Any]] = []
    for machine in machines:
        health = machine.get("health") or {}
        hosts.append(
            {
                "host_id": machine.get("id", ""),
                "kernel_log_available": _has_kernel_log_signal(health if isinstance(health, dict) else {}),
            }
        )

    if not any(host["kernel_log_available"] for host in hosts):
        skip = skip_result(
            args.site_id,
            "NICo health API does not expose BMC kernel log messages on the tenant REST surface (BFX03-03 gap)",
            gap="BFX03-03",
        )
        skip["hosts"] = hosts
        return emit(skip)

    result["hosts"] = hosts
    return emit(result)


if __name__ == "__main__":
    sys.exit(main())
