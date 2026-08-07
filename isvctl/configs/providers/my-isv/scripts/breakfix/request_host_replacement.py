#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Request host replacement (BFX01-05) - my-isv template."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow importing provider-local helpers from scripts/common/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.stub import emit_stub


def main() -> int:
    """Emit the host-replacement request template result (BFX01-05)."""
    parser = argparse.ArgumentParser(description="Request host replacement (template)")
    parser.add_argument("--region", default="", help="Cloud region")
    parser.add_argument("--machine-id", default="", help="Target machine id")
    args = parser.parse_args()

    machine_id = args.machine_id or "demo-machine-001"
    return emit_stub(
        "request_host_replacement",
        hint="host replacement breakfix API",
        operation={
            "requested": True,
            "node_removed_from_pool": True,
            "machine_id": machine_id,
        },
    )


if __name__ == "__main__":
    sys.exit(main())
