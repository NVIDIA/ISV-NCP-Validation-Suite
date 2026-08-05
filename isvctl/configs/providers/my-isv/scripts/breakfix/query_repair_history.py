#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Query repair history (BFX02-03) - my-isv template."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stub import base_result, demo_or_not_implemented, finish


def main() -> int:
    """Emit the repair-history query template result (BFX02-03)."""
    parser = argparse.ArgumentParser(description="Query repair history (template)")
    parser.add_argument("--region", default="", help="Cloud region")
    _ = parser.parse_args()

    result = demo_or_not_implemented(
        {
            **base_result("query_repair_history"),
            "history_queryable": True,
            "records": [
                {
                    "machine_id": "demo-machine-001",
                    "entries": [
                        {
                            "status": "Repairing",
                            "message": "GPU replaced",
                            "updated_at": "2026-06-15T09:00:00Z",
                            "action": "repairs done on faulty GPUs",
                        }
                    ],
                }
            ],
        },
        hint="repair history query",
    )
    return finish(result)


if __name__ == "__main__":
    sys.exit(main())
