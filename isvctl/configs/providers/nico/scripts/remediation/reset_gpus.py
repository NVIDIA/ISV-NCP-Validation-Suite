#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""GPU reset (BFX01-01) - NICo gap (Maestro/k8s mutating workflow)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from remediation._common import emit, skip_result

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--org", required=True)
    p.add_argument("--site-id", required=True)
    p.add_argument("--api-base", required=True)
    a, _ = p.parse_known_args()
    r = skip_result(
        a.site_id,
        "GPU reset via breakfix API requires Maestro/k8s integration (BFX01-01 gap on NICo)",
        gap="BFX01-01",
    )
    r["operation"] = {"requested": False, "completed": False}
    sys.exit(emit(r))
