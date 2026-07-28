# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for my-isv remediation scaffold scripts."""

from __future__ import annotations

import json
import os
from typing import Any

DEMO_MODE = os.environ.get("ISVCTL_DEMO_MODE") == "1"


def finish(result: dict[str, Any]) -> int:
    """Print JSON result and return a process exit code."""
    print(json.dumps(result, indent=2))
    return 0 if result.get("success") else 1


def base_result(test_name: str) -> dict[str, Any]:
    return {"success": False, "platform": "my-isv", "test_name": test_name}


def demo_or_not_implemented(result: dict[str, Any], *, hint: str) -> dict[str, Any]:
    if DEMO_MODE:
        result["success"] = True
        return result
    result["error"] = f"Not implemented - replace with your platform's {hint}"
    return result
