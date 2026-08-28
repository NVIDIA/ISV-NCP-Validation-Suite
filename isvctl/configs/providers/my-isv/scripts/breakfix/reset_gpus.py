#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Request a GPU reset on an operator-managed node (BFX01-01) - my-isv template.

Empty shell: no provider exposes an on-demand GPU reset, so there is no working
implementation to copy here yet.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow importing provider-local helpers from scripts/common/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.stub import emit_stub


def main() -> int:
    """Emit the GPU reset request template result (BFX01-01)."""
    parser = argparse.ArgumentParser(description="Request a GPU reset via the breakfix API (template)")
    parser.add_argument("--region", default="", help="Cloud region")
    parser.add_argument("--machine-id", default="", help="Target machine/node id")
    args = parser.parse_args()

    node_id = args.machine_id or "demo-node-001"
    # request_id is the handle the tenant polls: the reset itself completes
    # asynchronously, so the step reports acceptance rather than completion.
    return emit_stub(
        "reset_gpus",
        hint="GPU reset request API",
        operation={
            "requested": True,
            "accepted": True,
            "node_id": node_id,
            "gpu_ids": ["GPU-00000000-0000-0000-0000-000000000000"],
            "request_id": "demo-reset-request-001",
        },
    )


if __name__ == "__main__":
    sys.exit(main())
