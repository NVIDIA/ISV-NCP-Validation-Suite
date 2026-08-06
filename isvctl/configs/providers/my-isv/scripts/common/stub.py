# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Emit the scaffold result payload every my-isv template script produces.

A scaffold script is a placeholder: on a real run it reports that the ISV has
not implemented the step yet, and under ``ISVCTL_DEMO_MODE=1`` it reports the
dummy success that lets ``make demo-test`` exercise the wiring end to end.
Both shapes are the same JSON contract, so they live in one helper here rather
than being restated per script.
"""

from __future__ import annotations

import json
import os
from typing import Any

# ISVCTL_DEMO_MODE=1 enables demo-success output (used by `make demo-test`).
DEMO_MODE = os.environ.get("ISVCTL_DEMO_MODE") == "1"


def emit_stub(test_name: str, *, hint: str, **payload: Any) -> int:
    """Print the scaffold result as JSON and return a process exit code.

    Args:
        test_name: Step name, echoed back as ``test_name`` in the payload.
        hint: What the ISV should implement, named in the not-implemented error.
        payload: Contract fields the bound validation reads, emitted as-is so a
            demo run produces a realistic result.

    Returns:
        0 in demo mode, 1 otherwise (the step is not implemented).
    """
    result: dict[str, Any] = {
        "success": DEMO_MODE,
        "platform": "my-isv",
        "test_name": test_name,
        **payload,
    }
    if not DEMO_MODE:
        result["error"] = f"Not implemented - replace with your platform's {hint}"
    print(json.dumps(result, indent=2))
    return 0 if DEMO_MODE else 1
