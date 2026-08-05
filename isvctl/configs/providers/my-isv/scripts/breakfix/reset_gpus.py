#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Reset GPUs on a node (BFX01-01) - my-isv template."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stub import base_result, demo_or_not_implemented, finish


def main() -> int:
    """Emit the GPU reset template result (BFX01-01)."""
    parser = argparse.ArgumentParser(description="Reset GPUs via breakfix API (template)")
    parser.add_argument("--region", default="", help="Cloud region")
    parser.add_argument("--machine-id", default="", help="Target machine/node id")
    args = parser.parse_args()

    node_id = args.machine_id or "demo-node-001"
    result = demo_or_not_implemented(
        {
            **base_result("reset_gpus"),
            "operation": {"requested": True, "completed": True, "node_id": node_id, "machine_id": node_id},
        },
        hint="GPU reset breakfix API",
    )
    return finish(result)


if __name__ == "__main__":
    sys.exit(main())
