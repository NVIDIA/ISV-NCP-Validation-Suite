#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Query the GPU health monitoring process on each node (BFX04-01) - my-isv template."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow importing provider-local helpers from scripts/common/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.stub import emit_stub


def main() -> int:
    """Emit the node health-agent query template result (BFX04-01)."""
    parser = argparse.ArgumentParser(description="Query node health agents (template)")
    parser.add_argument("--region", default="", help="Cloud region")
    _ = parser.parse_args()

    return emit_stub(
        "query_node_health_agents",
        hint="GPU health monitoring process probe",
        agents_observable=True,
        # agent_name must hold whichever process this platform actually found:
        # the check accepts any name but rejects a running record without one.
        agents=[{"node_id": "demo-node-001", "agent_name": "nvsentinel", "running": True}],
    )


if __name__ == "__main__":
    sys.exit(main())
