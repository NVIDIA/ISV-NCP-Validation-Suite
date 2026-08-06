#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Return rack for maintenance (BFX01-03) - my-isv template."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow importing provider-local helpers from scripts/common/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.stub import emit_stub


def main() -> int:
    """Emit the return-rack-for-maintenance template result (BFX01-03)."""
    parser = argparse.ArgumentParser(description="Return rack for maintenance (template)")
    parser.add_argument("--region", default="", help="Cloud region")
    parser.add_argument("--rack-id", default="", help="Target rack id")
    args = parser.parse_args()

    rack_id = args.rack_id or "demo-rack-001"
    return emit_stub(
        "return_rack_maintenance",
        hint="return-rack-for-maintenance API",
        operation={"requested": True, "accepted": True, "rack_id": rack_id},
    )


if __name__ == "__main__":
    sys.exit(main())
