#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Inspect GB300 NVSwitch tray firmware with read-only ``nvfwupd`` (BFX03-02).

The script is intended to run on a GB300 BCM head. It discovers dedicated
``nvswitch`` devices through read-only ``cmsh`` inventory and invokes only
``nvfwupd show_version -j`` against the selected tray BMCs. Credentials remain
inside the privileged subprocess and are never included in the JSON result.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Sequence
from typing import Any

_HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
MAX_SWITCH_LIMIT = 8
_NVFWUPD_PATH = "/cm/local/apps/cm-nvfwupd/nvfwupd"
_SERVER_TYPE = "gb200switch"
_MODULE_SETUP = """\
export MODULEPATH=/cm/local/modulefiles:/cm/shared/modulefiles
source /cm/local/apps/environment-modules/current/init/bash
module load shared cmsh cm-nvfwupd >/dev/null 2>&1
"""
_DISCOVER_SCRIPT = (
    _MODULE_SETUP
    + """\
exec cmsh-lazy-load -c 'device; list -t switch -f hostname:64,category:32,status:32'
"""
)
_QUERY_SCRIPT = (
    _MODULE_SETUP
    + f"""\
switch_host="$1"
bmc_creds=$(cmsh-lazy-load -c "device; use $switch_host; get ip; accesssettings; get username; get password")
set -- $bmc_creds
if [ "$#" -lt 3 ]; then
    exit 20
fi
bmc_ip="$1"
bmc_user="$2"
bmc_pass="$3"
exec {_NVFWUPD_PATH} \\
    -t ip="$bmc_ip" user="$bmc_user" password="$bmc_pass" servertype={_SERVER_TYPE} \\
    show_version -j
"""
)


class InspectionError(RuntimeError):
    """Raised when direct NVSwitch firmware evidence cannot be obtained."""


class ProviderArgumentParser(argparse.ArgumentParser):
    """Raise provider errors instead of exiting without a JSON result."""

    def error(self, message: str) -> None:
        """Convert invalid arguments into the provider failure path."""
        raise InspectionError(f"Invalid arguments: {message}")


def _emit(result: dict[str, Any]) -> int:
    """Print the provider-neutral JSON result and return its exit status."""
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("success") else 1


def _run_privileged(script: str, *args: str, timeout: int) -> subprocess.CompletedProcess[str]:
    """Run one fixed read-only helper as root without exposing BMC credentials."""
    return subprocess.run(
        ["sudo", "-n", "bash", "-s", "--", *args],
        input=script,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def _validate_host(host: str) -> str:
    """Reject values that cannot be safely used as BCM device names."""
    value = host.strip()
    if not _HOST_RE.fullmatch(value):
        raise InspectionError("invalid NVSwitch hostname")
    return value


def _discover_switches(rack: str) -> list[str]:
    """Return dedicated NVSwitch hostnames from BCM's read-only inventory."""
    completed = _run_privileged(_DISCOVER_SCRIPT, timeout=30)
    if completed.returncode != 0:
        raise InspectionError("unable to read NVSwitch inventory from BCM")

    rack_prefix = rack.strip().lower()
    switches: list[str] = []
    for line in completed.stdout.splitlines():
        fields = line.split()
        if len(fields) < 2 or "nvswitch" not in fields[1].lower():
            continue
        host = _validate_host(fields[0])
        if rack_prefix and not host.lower().startswith(f"{rack_prefix}-"):
            continue
        if host not in switches:
            switches.append(host)
    return switches


def _query_tray(host: str) -> dict[str, Any]:
    """Run ``nvfwupd show_version -j`` against one dedicated switch tray."""
    completed = _run_privileged(_QUERY_SCRIPT, _validate_host(host), timeout=120)
    if completed.returncode != 0:
        raise InspectionError("nvfwupd show_version failed")
    try:
        inventory = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise InspectionError("nvfwupd returned invalid JSON") from exc
    if not isinstance(inventory, dict) or str(inventory.get("Error Code", 0)) != "0":
        raise InspectionError("nvfwupd returned a firmware inventory error")

    devices = inventory.get("Firmware Devices")
    if not isinstance(devices, list) or not devices:
        raise InspectionError("nvfwupd returned no firmware devices")

    versions: dict[str, str] = {}
    incomplete_inventory = False
    for device in devices:
        if not isinstance(device, dict):
            raise InspectionError("nvfwupd returned a malformed firmware device")
        raw_name = device.get("AP Name")
        raw_version = device.get("Sys Version")
        if not isinstance(raw_name, str):
            raise InspectionError("nvfwupd returned a firmware device without a name")
        name = raw_name.strip()
        if not name:
            raise InspectionError("nvfwupd returned a firmware device without a name")
        if raw_version is not None and not isinstance(raw_version, str):
            raise InspectionError("nvfwupd returned a malformed firmware version")
        version = raw_version.strip() if raw_version is not None else ""
        if not version:
            incomplete_inventory = True
        versions[name] = version

    primary_version = (
        "" if incomplete_inventory else versions.get("BMC") or versions.get("ASIC") or next(iter(versions.values()))
    )
    return {
        "tray_id": host,
        "firmware_version": primary_version,
        "firmware_versions": versions,
    }


def _configured_switches(cli_switches: Sequence[str]) -> list[str]:
    """Normalize configured switch targets while preserving their order."""
    configured = list(cli_switches)
    switches: list[str] = []
    for candidate in configured:
        if not candidate.strip():
            continue
        host = _validate_host(candidate)
        if host not in switches:
            switches.append(host)
    return switches


def _bounded_limit(value: str) -> int:
    """Parse a positive tray limit bounded by the executor timeout."""
    parsed = int(value)
    if not 1 <= parsed <= MAX_SWITCH_LIMIT:
        raise argparse.ArgumentTypeError(f"must be between 1 and {MAX_SWITCH_LIMIT}")
    return parsed


def main() -> int:
    """Inspect selected GB300 NVSwitch trays and emit BFX03-02 evidence."""
    parser = ProviderArgumentParser(description="Inspect GB300 NVSwitch tray firmware with nvfwupd")
    parser.add_argument("--rack", default="", help="BCM rack hostname prefix")
    parser.add_argument("--switch-host", action="append", default=[], help="NVSwitch hostname; repeat as needed")
    parser.add_argument("--switch-hosts", default="", help="Comma-separated NVSwitch hostnames")
    parser.add_argument(
        "--limit",
        type=_bounded_limit,
        default=1,
        help=f"Maximum number of trays to inspect, 1-{MAX_SWITCH_LIMIT} (default: 1)",
    )

    result: dict[str, Any] = {
        "success": False,
        "platform": "gb300",
        "source": "nvfwupd show_version -j",
        "trays": [],
    }
    try:
        args = parser.parse_args()
        switches = _configured_switches([*args.switch_host, *args.switch_hosts.split(",")])
        if not switches:
            switches = _discover_switches(args.rack)
        if not switches:
            raise InspectionError("no NVSwitch trays discovered on the GB300 system")
        result["trays"] = [_query_tray(host) for host in switches[: args.limit]]
    except (InspectionError, subprocess.TimeoutExpired) as exc:
        result["error_type"] = "firmware_inspection"
        result["error"] = str(exc) if isinstance(exc, InspectionError) else "NVSwitch firmware inspection timed out"
        return _emit(result)

    result["success"] = True
    return _emit(result)


if __name__ == "__main__":
    sys.exit(main())
