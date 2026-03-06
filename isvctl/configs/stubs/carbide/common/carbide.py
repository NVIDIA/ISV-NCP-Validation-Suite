# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Shared helpers for Carbide CLI (carbidecli) stub scripts.

Provides:
  - run_carbide(): Execute carbidecli commands with JSON output parsing
  - timed_call(): Same as run_carbide but also returns latency
  - load_state() / save_state(): Persist data between steps via JSON file

Environment:
  carbidecli handles authentication via its own config (~/.carbide/config.yaml)
  or environment variables (CARBIDE_TOKEN, CARBIDE_API_KEY, CARBIDE_ORG, etc.).
"""

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any


DEFAULT_STATE_FILE = "/tmp/ncp-carbide-state.json"


def run_carbide(*args: str, timeout: int = 120) -> dict[str, Any]:
    """Run a carbidecli command and return parsed JSON output.

    Args:
        *args: Command arguments (e.g., "tenant", "get")
        timeout: Command timeout in seconds

    Returns:
        Parsed JSON output from carbidecli

    Raises:
        RuntimeError: If the command fails or returns non-JSON output
    """
    cmd = ["carbidecli", "-o", "json"] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    if result.returncode != 0:
        raise RuntimeError(f"carbidecli {' '.join(args)} failed: {result.stderr.strip()}")

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"carbidecli returned non-JSON output: {result.stdout[:500]}")


def timed_call(*args: str, timeout: int = 120) -> tuple[dict[str, Any], float]:
    """Run a carbidecli command and return (result, latency_seconds)."""
    start = time.monotonic()
    data = run_carbide(*args, timeout=timeout)
    elapsed = time.monotonic() - start
    return data, elapsed


def load_state(state_file: str | None = None) -> dict[str, Any]:
    """Load persisted state from a JSON file."""
    path = Path(state_file or os.environ.get("CARBIDE_STATE_FILE", DEFAULT_STATE_FILE))
    if path.exists():
        return json.loads(path.read_text())
    return {}


def save_state(state: dict[str, Any], state_file: str | None = None) -> None:
    """Save state to a JSON file for use by subsequent steps."""
    path = Path(state_file or os.environ.get("CARBIDE_STATE_FILE", DEFAULT_STATE_FILE))
    path.write_text(json.dumps(state, indent=2))
