#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Return node for maintenance (BFX01-02) - my-isv template."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stub import base_result, demo_or_not_implemented, finish


def main() -> int:
    parser = argparse.ArgumentParser(description="Return node for maintenance (template)")
    parser.add_argument("--region", default="", help="Cloud region")
    parser.add_argument("--machine-id", default="", help="Target machine id")
    args = parser.parse_args()

    machine_id = args.machine_id or "demo-machine-001"
    result = demo_or_not_implemented(
        {
            **base_result("return_node_maintenance"),
            "operation": {
                "requested": True,
                "accepted": True,
                "machine_id": machine_id,
                "maintenance_mode": True,
            },
        },
        hint="return-node-for-maintenance API",
    )
    return finish(result)


if __name__ == "__main__":
    sys.exit(main())
