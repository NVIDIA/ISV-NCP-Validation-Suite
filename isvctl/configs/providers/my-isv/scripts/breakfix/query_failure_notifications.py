#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Query immediate failure notifications (BFX06-01) - my-isv template."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stub import base_result, demo_or_not_implemented, finish


def main() -> int:
    parser = argparse.ArgumentParser(description="Query failure notifications (template)")
    parser.add_argument("--region", default="", help="Cloud region")
    _ = parser.parse_args()

    result = demo_or_not_implemented(
        {
            **base_result("query_failure_notifications"),
            "notification_channel_observable": True,
            "sample_event": {"type": "node_failure", "node_id": "demo-node-001"},
        },
        hint="immediate failure notification channel",
    )
    return finish(result)


if __name__ == "__main__":
    sys.exit(main())
