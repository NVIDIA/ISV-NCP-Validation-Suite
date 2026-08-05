#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Request host replacement (BFX01-05) - my-isv template."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stub import base_result, demo_or_not_implemented, finish


def main() -> int:
    """Emit the host-replacement request template result (BFX01-05)."""
    parser = argparse.ArgumentParser(description="Request host replacement (template)")
    parser.add_argument("--region", default="", help="Cloud region")
    parser.add_argument("--machine-id", default="", help="Target machine id")
    args = parser.parse_args()

    machine_id = args.machine_id or "demo-machine-001"
    result = demo_or_not_implemented(
        {
            **base_result("request_host_replacement"),
            "operation": {
                "requested": True,
                "node_removed_from_pool": True,
                "machine_id": machine_id,
            },
        },
        hint="host replacement breakfix API",
    )
    return finish(result)


if __name__ == "__main__":
    sys.exit(main())
