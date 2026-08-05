#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Query node health agents GPUd/Sentinel (BFX04-01) - my-isv template."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stub import base_result, demo_or_not_implemented, finish


def main() -> int:
    """Emit the node health-agent query template result (BFX04-01)."""
    parser = argparse.ArgumentParser(description="Query node health agents (template)")
    parser.add_argument("--region", default="", help="Cloud region")
    _ = parser.parse_args()

    result = demo_or_not_implemented(
        {
            **base_result("query_node_health_agents"),
            "agents_observable": True,
            "agents": [{"node_id": "demo-node-001", "agent_name": "sentinel", "running": True}],
        },
        hint="GPUd/Sentinel health agent probe",
    )
    return finish(result)


if __name__ == "__main__":
    sys.exit(main())
