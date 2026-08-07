#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Cordon a Kubernetes node (BFX01-04) - my-isv template."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow importing provider-local helpers from scripts/common/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.stub import emit_stub


def main() -> int:
    """Emit the cordon-node template result (BFX01-04)."""
    parser = argparse.ArgumentParser(description="Cordon node (template)")
    parser.add_argument("--region", default="", help="Cloud region")
    _ = parser.parse_args()

    return emit_stub(
        "cordon_node",
        hint="cordon node breakfix API",
        operation={
            "cordoned": True,
            "new_workloads_blocked": True,
            "existing_workloads_running": True,
        },
    )


if __name__ == "__main__":
    sys.exit(main())
