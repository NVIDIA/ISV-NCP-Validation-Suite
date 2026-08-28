#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Query immediate failure notifications (BFX06-01) - my-isv template."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow importing provider-local helpers from scripts/common/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.stub import emit_stub


def main() -> int:
    """Emit the immediate-failure notification template result (BFX06-01)."""
    parser = argparse.ArgumentParser(description="Query failure notifications (template)")
    parser.add_argument("--region", default="", help="Cloud region")
    _ = parser.parse_args()

    return emit_stub(
        "query_failure_notifications",
        hint="immediate failure notification channel",
        notification_channel_observable=True,
        # detected_at to notified_at is the latency "immediate" is measured by.
        notifications=[
            {
                "machine_id": "demo-machine-001",
                "type": "node_failure",
                "message": "Node became unreachable; GPU fault detected",
                "detected_at": "2026-06-24T11:59:30Z",
                "notified_at": "2026-06-24T12:00:00Z",
            }
        ],
    )


if __name__ == "__main__":
    sys.exit(main())
