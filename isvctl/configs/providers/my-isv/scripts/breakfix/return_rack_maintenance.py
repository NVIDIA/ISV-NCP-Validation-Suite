#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Return rack for maintenance (BFX01-03) - my-isv template."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stub import base_result, demo_or_not_implemented, finish


def main() -> int:
    """Emit the return-rack-for-maintenance template result (BFX01-03)."""
    parser = argparse.ArgumentParser(description="Return rack for maintenance (template)")
    parser.add_argument("--region", default="", help="Cloud region")
    parser.add_argument("--rack-id", default="", help="Target rack id")
    args = parser.parse_args()

    rack_id = args.rack_id or "demo-rack-001"
    result = demo_or_not_implemented(
        {
            **base_result("return_rack_maintenance"),
            "operation": {"requested": True, "accepted": True, "rack_id": rack_id},
        },
        hint="return-rack-for-maintenance API",
    )
    return finish(result)


if __name__ == "__main__":
    sys.exit(main())
