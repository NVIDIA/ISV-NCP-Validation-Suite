#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Read-only reference implementation of the BFX04-01 node-health-agent query.

Reports, per configured GPU node, whether a supported NVIDIA node-health agent
is running: NVIDIA Fleet Intelligence Agent (GPUd) or the NVSentinel GPU Health
Monitor. Evidence comes from ``systemctl is-active`` over SSH, so it works on
any bare-metal fleet whose control-plane API does not expose agent state.

Nodes are named through ``--nodes``. With none configured the step emits a
structured skip: an unconfigured site is indistinguishable from one with no
agents, and a pass there would assert nothing.

Probes fan out across nodes because they are dominated by SSH round-trip
latency. A serial probe of a full rack would outlive the step timeout and the
executor would kill the process before it could emit its JSON contract.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any

TEST_NAME = "query_node_health_agents"

# systemd units shipped by the two agents BFX04-01 accepts. Generic GPU
# telemetry (a DCGM exporter, say) is deliberately absent: it reports metrics
# but performs none of the health detection the requirement is about.
AGENT_UNITS = ("fleetintd", "gpud", "nvsentinel", "gpu-health-monitor")

# SSH targets must be bare host names or addresses. Anything else could be read
# by ssh(1) as an option (`-oProxyCommand=...`) or by the remote shell.
NODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

CONNECT_TIMEOUT_SECONDS = 10
PROBE_TIMEOUT_SECONDS = 20
MAX_CONCURRENT_PROBES = 8


class NodeHealthQueryError(RuntimeError):
    """Raised when a node's health-agent state cannot be determined."""


class ProviderArgumentParser(argparse.ArgumentParser):
    """Raise provider errors instead of exiting without a JSON result."""

    def error(self, message: str) -> None:
        """Convert invalid arguments into the provider failure path."""
        raise NodeHealthQueryError(f"Invalid arguments: {message}")


def _parse_nodes(value: str) -> list[str]:
    """Return the de-duplicated node list, rejecting unsafe SSH targets."""
    nodes = list(dict.fromkeys(part for part in re.split(r"[\s,]+", value) if part))
    if any(not NODE_PATTERN.fullmatch(node) for node in nodes):
        raise NodeHealthQueryError("Invalid bare-metal node name")
    return nodes


def _active_unit(node: str) -> str:
    """Return the supported agent unit active on ``node``, or an empty string.

    ``systemctl is-active`` prints one state per unit argument, in order, and
    exits non-zero unless every unit is active - so the exit status is not a
    useful signal here and the states are read positionally instead. ``|| true``
    keeps the remote shell's status clean so a non-zero status can only mean the
    SSH transport itself failed.
    """
    remote_command = f"systemctl is-active {' '.join(AGENT_UNITS)} 2>/dev/null || true"
    command = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={CONNECT_TIMEOUT_SECONDS}",
        # Before the host, not after: ssh only stops option parsing at a `--`
        # that precedes its first non-option argument.
        "--",
        node,
        remote_command,
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise NodeHealthQueryError(f"Health agent query failed for {node}") from exc
    if completed.returncode != 0:
        raise NodeHealthQueryError(f"Health agent query failed for {node}")

    states = completed.stdout.split()
    if len(states) != len(AGENT_UNITS):
        raise NodeHealthQueryError(f"Health agent query returned an unreadable status for {node}")
    return next((unit for unit, state in zip(AGENT_UNITS, states, strict=True) if state == "active"), "")


def _probe(node: str) -> str | None:
    """Return the active agent unit, or None when the node yielded no evidence.

    A node we could not read is not a node without an agent, so it must not
    become a ``running: False`` record: the check reads only that flag, and
    would report a missing agent on a host it never reached.
    """
    try:
        return _active_unit(node)
    except NodeHealthQueryError:
        return None


def _query(nodes: list[str]) -> dict[str, Any]:
    """Return provider-neutral BFX04-01 evidence for every configured node."""
    if not nodes:
        return {
            "success": True,
            "platform": "bare_metal",
            "test_name": TEST_NAME,
            "skipped": True,
            "skip_reason": "No GPU nodes configured for health-agent inspection",
            "agents_observable": False,
            "agents": [],
        }
    with ThreadPoolExecutor(max_workers=min(MAX_CONCURRENT_PROBES, len(nodes))) as pool:
        units = list(pool.map(_probe, nodes))
    # Every unreadable node is named, so a fleet-wide access problem takes one
    # run to diagnose rather than one run per node.
    unreadable = [node for node, unit in zip(nodes, units, strict=True) if unit is None]
    if unreadable:
        raise NodeHealthQueryError(f"Health agent query failed for {len(unreadable)} node(s): {', '.join(unreadable)}")
    return {
        "success": True,
        "platform": "bare_metal",
        "test_name": TEST_NAME,
        "agents_observable": True,
        "agents": [
            {"node_id": node, "agent_name": unit, "running": bool(unit)}
            for node, unit in zip(nodes, units, strict=True)
        ],
    }


def main() -> int:
    """Emit one structured BFX04-01 result for the configured nodes."""
    parser = ProviderArgumentParser(description="Query NVIDIA node-health agents")
    parser.add_argument(
        "--nodes",
        default="",
        help="Comma-separated GPU nodes to inspect over SSH",
    )
    try:
        args = parser.parse_args()
        result = _query(_parse_nodes(args.nodes))
    except NodeHealthQueryError as exc:
        result = {
            "success": False,
            "platform": "bare_metal",
            "test_name": TEST_NAME,
            "error_type": "node_health_query_failed",
            "error": str(exc),
        }
    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
