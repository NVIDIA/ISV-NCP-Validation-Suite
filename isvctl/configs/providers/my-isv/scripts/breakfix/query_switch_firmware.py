#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Query NV switch tray firmware (BFX03-02) - my-isv template."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow importing provider-local helpers from scripts/common/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.stub import emit_stub


def main() -> int:
    """Emit the NV switch firmware query template result (BFX03-02)."""
    parser = argparse.ArgumentParser(description="Query NV switch firmware (template)")
    parser.add_argument("--region", default="", help="Cloud region")
    _ = parser.parse_args()

    return emit_stub(
        "query_switch_firmware",
        hint="NV switch tray firmware query",
        trays=[{"tray_id": "nvsw-001", "firmware_version": "1.0.0-demo"}],
    )


if __name__ == "__main__":
    sys.exit(main())
