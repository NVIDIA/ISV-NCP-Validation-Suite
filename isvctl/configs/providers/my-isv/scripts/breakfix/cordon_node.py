#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Cordon a Kubernetes node (BFX01-04) - my-isv template."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stub import base_result, demo_or_not_implemented, finish


def main() -> int:
    """Emit the cordon-node template result (BFX01-04)."""
    parser = argparse.ArgumentParser(description="Cordon node (template)")
    parser.add_argument("--region", default="", help="Cloud region")
    _ = parser.parse_args()

    result = demo_or_not_implemented(
        {
            **base_result("cordon_node"),
            "operation": {
                "cordoned": True,
                "new_workloads_blocked": True,
                "existing_workloads_running": True,
            },
        },
        hint="cordon node breakfix API",
    )
    return finish(result)


if __name__ == "__main__":
    sys.exit(main())
