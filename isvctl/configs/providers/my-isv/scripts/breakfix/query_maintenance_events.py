#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Query maintenance events (BFX02-01) - my-isv template."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow importing provider-local helpers from scripts/common/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.stub import emit_stub


def main() -> int:
    """Emit the maintenance-event query template result (BFX02-01)."""
    parser = argparse.ArgumentParser(description="Query maintenance events (template)")
    parser.add_argument("--region", default="", help="Cloud region")
    _ = parser.parse_args()

    return emit_stub(
        "query_maintenance_events",
        hint="maintenance events query",
        events_queryable=True,
        events=[
            {
                "machine_id": "demo-machine-001",
                "status": "maintenance",
                "message": "Scheduled firmware update",
            }
        ],
    )


if __name__ == "__main__":
    sys.exit(main())
