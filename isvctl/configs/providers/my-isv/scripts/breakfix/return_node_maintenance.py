#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Return node for maintenance (BFX01-02) - my-isv template."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow importing provider-local helpers from scripts/common/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.stub import emit_stub


def main() -> int:
    """Emit the return-node-for-maintenance template result (BFX01-02)."""
    parser = argparse.ArgumentParser(description="Return node for maintenance (template)")
    parser.add_argument("--region", default="", help="Cloud region")
    parser.add_argument("--machine-id", default="", help="Target machine id")
    args = parser.parse_args()

    machine_id = args.machine_id or "demo-machine-001"
    # Returning a node has to leave it out of service: a machine that goes
    # straight back into the pool was deleted, not returned for maintenance.
    return emit_stub(
        "return_node_maintenance",
        hint="return-node-for-maintenance API (relinquish the instance, quarantine the machine)",
        operation={
            "requested": True,
            "accepted": True,
            "instance_deleted": True,
            "machine_quarantined": True,
            "instance_id": "demo-instance-001",
            "machine_id": machine_id,
        },
    )


if __name__ == "__main__":
    sys.exit(main())
