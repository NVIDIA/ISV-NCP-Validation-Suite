#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Query repair history (BFX02-03) - my-isv template."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow importing provider-local helpers from scripts/common/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.stub import emit_stub


def main() -> int:
    """Emit the repair-history query template result (BFX02-03)."""
    parser = argparse.ArgumentParser(description="Query repair history (template)")
    parser.add_argument("--region", default="", help="Cloud region")
    _ = parser.parse_args()

    return emit_stub(
        "query_repair_history",
        hint="repair history query",
        history_queryable=True,
        records=[
            {
                "machine_id": "demo-machine-001",
                "entries": [
                    {
                        "status": "Repairing",
                        "message": "GPU replaced",
                        "updated_at": "2026-06-15T09:00:00Z",
                    }
                ],
            }
        ],
    )


if __name__ == "__main__":
    sys.exit(main())
