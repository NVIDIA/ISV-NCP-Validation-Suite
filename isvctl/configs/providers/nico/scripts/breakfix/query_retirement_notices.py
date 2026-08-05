#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Query retirement notices (BFX02-02) - NICo gap stub.

NICo exposes maintenance and repair signals on the machine resource but does
not yet expose a dedicated retirement-notice query API matching the offtake BFX02
event schema.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from breakfix._common import emit, skip_result


def main() -> int:
    """Emit the retirement-notice gap payload for NICo as JSON (BFX02-02)."""
    parser = argparse.ArgumentParser(description="Query retirement notices (NICo)")
    parser.add_argument("--org", required=True)
    parser.add_argument("--site-id", required=True)
    parser.add_argument("--api-base", required=True)
    args = parser.parse_args()

    result = skip_result(
        args.site_id,
        "NICo has no retirement-notice query API (BFX02-02 gap)",
        gap="BFX02-02",
    )
    result["notices_queryable"] = False
    result["notices"] = []
    return emit(result)


if __name__ == "__main__":
    sys.exit(main())
