#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""GPU reset stub (BFX01-01) - my-isv template.

Replace this script with your platform's GPU reset implementation, or point
the config command at isvctl/configs/providers/shared/reset_gpus.py if your
provider uses SSH-based reset (see aws/config/gpu_reset.yaml for an example).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow importing provider-local helpers from scripts/common/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.stub import emit_stub


def main() -> int:
    """Emit the GPU-reset template result (BFX01-01)."""
    parser = argparse.ArgumentParser(description="GPU reset (template)")
    parser.add_argument("--host", default="", help="Target node IP or hostname")
    parser.add_argument("--machine-id", default="", help="Kubernetes node name")
    parser.add_argument("--ssh-user", default="", help="SSH user")
    parser.add_argument("--ssh-key", default="", help="Path to SSH private key")
    parser.add_argument("--region", default="", help="Cloud region")
    _ = parser.parse_args()

    return emit_stub(
        "reset_gpus",
        hint="GPU reset API or SSH-based reset via shared/reset_gpus.py",
        operation={
            "requested": True,
            "completed": True,
            "flr_reset": False,
            "node_id": "demo-node",
            "message": "demo reset ok",
        },
    )


if __name__ == "__main__":
    sys.exit(main())
