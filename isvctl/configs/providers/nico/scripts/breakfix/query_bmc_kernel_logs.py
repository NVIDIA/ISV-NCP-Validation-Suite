#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Query a node's log history (BFX03-03) for NICo machines.

BFX03-03 asks for a queryable log history or stream -- OTEL, or an
OpenSearch/Kibana equivalent -- over a window the tenant chooses. NICo has no
such endpoint: it folds BMC telemetry into per-machine health probes, which
report that a signal exists, not what it said or when.

So this always emits a structured skip. It still inspects the probes and
reports which hosts carry a BMC log signal, because "NICo sees something here"
is useful context for whoever implements the real endpoint -- but that is
diagnostic output, deliberately named apart from the ``hosts`` contract
``BmcKernelLogCheck`` reads, so it cannot be mistaken for satisfying it.
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
    """Emit the BFX03-03 gap, with per-host BMC probe signals as context."""
    parser = argparse.ArgumentParser(description="Query a node's log history (NICo)")
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

    probes: list[dict[str, Any]] = []
    for machine in machines:
        health = machine.get("health") or {}
        probes.append(
            {
                "host_id": machine.get("id", ""),
                "bmc_log_probe_present": _has_kernel_log_signal(health if isinstance(health, dict) else {}),
            }
        )

    skip = skip_result(
        args.site_id,
        "NICo exposes no queryable log history or streaming endpoint on the tenant REST surface; "
        "BMC telemetry is only summarised into health probes (BFX03-03 gap)",
        gap="BFX03-03",
    )
    skip["hosts"] = []
    skip["bmc_probe_signals"] = probes
    return emit(skip)


if __name__ == "__main__":
    sys.exit(main())
