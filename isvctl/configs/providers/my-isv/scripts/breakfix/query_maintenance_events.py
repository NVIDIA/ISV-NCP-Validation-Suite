#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Query maintenance events (BFX02-01) - my-isv template."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stub import base_result, demo_or_not_implemented, finish


def main() -> int:
    """Emit the maintenance-event query template result (BFX02-01)."""
    parser = argparse.ArgumentParser(description="Query maintenance events (template)")
    parser.add_argument("--region", default="", help="Cloud region")
    args = parser.parse_args()

    result = demo_or_not_implemented(
        {
            **base_result("query_maintenance_events"),
            "events_queryable": True,
            "events": [
                {
                    "machine_id": "demo-machine-001",
                    "hardware_id": "demo-machine-001",
                    "status": "maintenance",
                    "message": "Scheduled firmware update",
                    "opened_at": "2026-07-01T12:00:00Z",
                }
            ],
        },
        hint="maintenance events query",
    )
    _ = args
    return finish(result)


if __name__ == "__main__":
    sys.exit(main())
