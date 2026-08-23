#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Query planned maintenance notifications (BFX05-01) - my-isv template."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow importing provider-local helpers from scripts/common/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.stub import emit_stub


def main() -> int:
    """Emit the planned-maintenance notification template result (BFX05-01)."""
    parser = argparse.ArgumentParser(description="Query planned maintenance notifications (template)")
    parser.add_argument("--region", default="", help="Cloud region")
    _ = parser.parse_args()

    return emit_stub(
        "query_planned_notifications",
        hint="planned maintenance notification channel",
        notification_channel_observable=True,
        notifications=[
            {
                "machine_id": "demo-machine-001",
                "type": "planned_maintenance",
                "message": "Scheduled firmware update (demo)",
                "notified_at": "2026-06-24T12:00:00Z",
                "scheduled_at": "2026-06-25T12:00:00Z",
                "channel": "webhook",
                "delivery_status": "delivered",
                "delivery_id": "demo-planned-delivery-001",
            }
        ],
    )


if __name__ == "__main__":
    sys.exit(main())
