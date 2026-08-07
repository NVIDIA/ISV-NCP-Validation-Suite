#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Reset GPUs on a node (BFX01-01) - my-isv template."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow importing provider-local helpers from scripts/common/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.stub import emit_stub


def main() -> int:
    """Emit the GPU reset template result (BFX01-01)."""
    parser = argparse.ArgumentParser(description="Reset GPUs via breakfix API (template)")
    parser.add_argument("--region", default="", help="Cloud region")
    parser.add_argument("--machine-id", default="", help="Target machine/node id")
    args = parser.parse_args()

    node_id = args.machine_id or "demo-node-001"
    return emit_stub(
        "reset_gpus",
        hint="GPU reset breakfix API",
        operation={"requested": True, "completed": True, "node_id": node_id},
    )


if __name__ == "__main__":
    sys.exit(main())
