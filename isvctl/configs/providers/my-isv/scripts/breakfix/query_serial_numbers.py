#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Query hardware serial numbers (BFX03-01) - my-isv template."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow importing provider-local helpers from scripts/common/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.stub import emit_stub


def main() -> int:
    """Emit the hardware serial-number query template result (BFX03-01)."""
    parser = argparse.ArgumentParser(description="Query hardware serial numbers (template)")
    parser.add_argument("--region", default="", help="Cloud region")
    args = parser.parse_args()

    return emit_stub(
        "query_serial_numbers",
        hint="hardware serial inventory query",
        site_id=args.region or "demo-site",
        machines_checked=1,
        machines=[
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
    )


if __name__ == "__main__":
    sys.exit(main())
