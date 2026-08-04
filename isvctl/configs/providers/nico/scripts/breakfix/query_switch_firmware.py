#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Query NV switch tray firmware (BFX03-02) - NICo gap stub.

NV switch inventory/firmware is managed by nvswitch-manager and is not exposed
on the tenant machine REST API used by validation scripts.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from breakfix._common import emit, skip_result


def main() -> int:
    parser = argparse.ArgumentParser(description="Query NV switch firmware (NICo)")
    parser.add_argument("--org", required=True)
    parser.add_argument("--site-id", required=True)
    parser.add_argument("--api-base", required=True)
    args = parser.parse_args()

    result = skip_result(
        args.site_id,
        "NV switch tray firmware is not queryable via NICo tenant REST API (BFX03-02 gap)",
        gap="BFX03-02",
    )
    result["trays"] = []
    return emit(result)


if __name__ == "__main__":
    sys.exit(main())
