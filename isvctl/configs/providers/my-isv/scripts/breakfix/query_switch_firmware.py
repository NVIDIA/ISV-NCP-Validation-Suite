#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Query NV switch tray firmware (BFX03-02) - my-isv template."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stub import base_result, demo_or_not_implemented, finish


def main() -> int:
    parser = argparse.ArgumentParser(description="Query NV switch firmware (template)")
    parser.add_argument("--region", default="", help="Cloud region")
    _ = parser.parse_args()

    result = demo_or_not_implemented(
        {
            **base_result("query_switch_firmware"),
            "trays": [{"tray_id": "nvsw-001", "firmware_version": "1.0.0-demo"}],
        },
        hint="NV switch tray firmware query",
    )
    return finish(result)


if __name__ == "__main__":
    sys.exit(main())
