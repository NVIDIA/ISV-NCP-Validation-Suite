#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Return rack for maintenance (BFX01-03) - NICo gap."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from breakfix._common import emit, skip_result

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--org", required=True)
    p.add_argument("--site-id", required=True)
    p.add_argument("--api-base", required=True)
    a, _ = p.parse_known_args()
    r = skip_result(
        a.site_id,
        "Rack-level maintenance return API is not exposed on NICo tenant REST (BFX01-03 gap)",
        gap="BFX01-03",
    )
    r["operation"] = {"requested": False, "accepted": False}
    sys.exit(emit(r))
