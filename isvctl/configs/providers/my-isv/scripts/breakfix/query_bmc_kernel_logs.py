#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Query a node's log history (BFX03-03) - my-isv template.

Empty shell: the requirement is a queryable log history or stream, not
serial-over-LAN console access. This script's name and ``BmcKernelLogCheck`` are
leftovers from that original BMC framing; the payload below is not.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow importing provider-local helpers from scripts/common/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.stub import emit_stub


def main() -> int:
    """Emit the BMC kernel-log query template result (BFX03-03)."""
    parser = argparse.ArgumentParser(description="Query BMC kernel logs (template)")
    parser.add_argument("--region", default="", help="Cloud region")
    _ = parser.parse_args()

    # The window is what makes this a log *history*: a provider must answer for
    # a period the tenant chose, not just tail whatever is happening now.
    return emit_stub(
        "query_bmc_kernel_logs",
        hint="node log history query (OTEL, OpenSearch, or equivalent)",
        hosts=[
            {
                "host_id": "demo-host-001",
                "window_start": "2026-06-24T00:00:00Z",
                "window_end": "2026-06-24T12:00:00Z",
                "entries_returned": 128,
            }
        ],
    )


if __name__ == "__main__":
    sys.exit(main())
