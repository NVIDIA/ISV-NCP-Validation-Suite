#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Query retirement notices (BFX02-02) - my-isv template."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stub import base_result, demo_or_not_implemented, finish


def main() -> int:
    """Emit the retirement-notice query template result (BFX02-02)."""
    parser = argparse.ArgumentParser(description="Query retirement notices (template)")
    parser.add_argument("--region", default="", help="Cloud region")
    _ = parser.parse_args()

    result = demo_or_not_implemented(
        {
            **base_result("query_retirement_notices"),
            "notices_queryable": True,
            "notices": [
                {
                    "machine_id": "demo-machine-001",
                    "rack_id": "demo-rack-001",
                    "status": "scheduled",
                    "message": "End-of-life retirement",
                    "retire_after": "2027-01-15T00:00:00Z",
                }
            ],
        },
        hint="retirement notices query",
    )
    return finish(result)


if __name__ == "__main__":
    sys.exit(main())
