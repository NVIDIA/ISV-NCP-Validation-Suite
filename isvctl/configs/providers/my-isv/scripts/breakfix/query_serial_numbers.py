#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Query hardware serial numbers (BFX03-01) - my-isv template."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stub import base_result, demo_or_not_implemented, finish


def main() -> int:
    """Emit the hardware serial-number query template result (BFX03-01)."""
    parser = argparse.ArgumentParser(description="Query hardware serial numbers (template)")
    parser.add_argument("--region", default="", help="Cloud region")
    args = parser.parse_args()

    result = demo_or_not_implemented(
        {
            **base_result("query_serial_numbers"),
            "site_id": args.region or "demo-site",
            "machines_checked": 1,
            "machines": [
                {
                    "machine_id": "demo-machine-001",
                    "components": {
                        "chassis": {"present": True, "identifiers": ["CH-DEMO-001"]},
                        "baseboard": {"present": True, "identifiers": ["BB-DEMO-001"]},
                        "cpu": {"present": True, "identifiers": ["Intel Demo CPU"]},
                        "gpu": {"present": True, "identifiers": ["GPU-DEMO-001"]},
                        "nic": {"present": True, "identifiers": ["aa:bb:cc:dd:ee:ff"]},
                    },
                }
            ],
        },
        hint="hardware serial inventory query",
    )
    return finish(result)


if __name__ == "__main__":
    sys.exit(main())
