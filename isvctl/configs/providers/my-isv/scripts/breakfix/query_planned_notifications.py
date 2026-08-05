#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Query planned maintenance notifications (BFX05-01) - my-isv template."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stub import base_result, demo_or_not_implemented, finish


def main() -> int:
    """Emit the planned-maintenance notification template result (BFX05-01)."""
    parser = argparse.ArgumentParser(description="Query planned maintenance notifications (template)")
    parser.add_argument("--region", default="", help="Cloud region")
    _ = parser.parse_args()

    result = demo_or_not_implemented(
        {
            **base_result("query_planned_notifications"),
            "notification_channel_observable": True,
            "sample_event": {"type": "planned_maintenance", "node_id": "demo-node-001"},
        },
        hint="planned maintenance notification channel",
    )
    return finish(result)


if __name__ == "__main__":
    sys.exit(main())
