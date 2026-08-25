# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for direct GB300 NVSwitch tray firmware inspection."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml
from isvtest.validations.breakfix import NvSwitchFirmwareCheck

from isvctl.config.merger import merge_yaml_files
from isvctl.config.schema import RunConfig
from isvctl.orchestrator.context import Context
from isvctl.orchestrator.step_executor import StepExecutor

ISVCTL_ROOT = Path(__file__).resolve().parents[3]
GB300_ROOT = ISVCTL_ROOT / "configs" / "providers" / "gb300"
SCRIPT_PATH = GB300_ROOT / "scripts" / "breakfix" / "query_switch_firmware.py"
CONFIG_PATH = GB300_ROOT / "config" / "bare_metal.yaml"

COMPLETE_INVENTORY = {
    "Error Code": 0,
    "Firmware Devices": [
        {"AP Name": "ASIC", "Sys Version": "1.0.0"},
        {"AP Name": "BIOS", "Sys Version": "2.0.0"},
        {"AP Name": "BMC", "Sys Version": "3.0.0"},
        {"AP Name": "CPLD1", "Sys Version": "4.0.0"},
        {"AP Name": "CPLD2", "Sys Version": "5.0.0"},
        {"AP Name": "CPLD3", "Sys Version": "6.0.0"},
        {"AP Name": "EROT", "Sys Version": "7.0.0"},
        {"AP Name": "FPGA", "Sys Version": "8.0.0"},
        {"AP Name": "SSD", "Sys Version": "9.0.0"},
    ],
}


def _load_script() -> ModuleType:
    """Load the provider script as an isolated module."""
    spec = importlib.util.spec_from_file_location("test_gb300_switch_firmware", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _completed(stdout: str, *, returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess[str]:
    """Build a subprocess result for privileged-helper mocks."""
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)


def test_config_wires_only_read_only_firmware_query() -> None:
    """The GB300 provider binds BFX03-02 to the direct query script."""
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    steps = config["commands"]["bare_metal"]["steps"]

    assert steps == [
        {
            "name": "query_switch_firmware",
            "phase": "test",
            "continue_on_failure": True,
            "command": "python ../scripts/breakfix/query_switch_firmware.py",
            "args": [
                "--rack={{ gb300_rack | default('', true) }}",
                "--switch-hosts={{ gb300_switch_hosts | default('', true) }}",
                "--limit={{ gb300_switch_limit | default(1, true) }}",
            ],
            "timeout": 1050,
        }
    ]
    assert config["tests"]["settings"]["gb300_rack"] == ""
    assert config["tests"]["settings"]["gb300_switch_hosts"] == ""
    assert config["tests"]["settings"]["gb300_switch_limit"] == 1


def test_configured_firmware_targets_render_from_test_settings() -> None:
    """GB300 targets and limits are regular YAML settings, not environment inputs."""
    merged = merge_yaml_files(
        [CONFIG_PATH],
        set_values=[
            "tests.settings.gb300_rack=rack-a",
            "tests.settings.gb300_switch_hosts=rack-a-nvsw-01,rack-a-nvsw-02",
            "tests.settings.gb300_switch_limit=2",
        ],
    )
    config = RunConfig.model_validate(merged)
    step = config.commands["bare_metal"].steps[0]

    assert StepExecutor()._render_args(step.args, Context(config)) == [
        "--rack=rack-a",
        "--switch-hosts=rack-a-nvsw-01,rack-a-nvsw-02",
        "--limit=2",
    ]


def test_discovers_dedicated_nvswitches_in_requested_rack(monkeypatch: pytest.MonkeyPatch) -> None:
    """BCM compute and other-rack devices never become firmware targets."""
    module = _load_script()
    inventory = """\
rack-a-compute-01 compute [ UP ]
rack-a-nvsw-01 nvswitch [ UP ]
rack-a-nvsw-02 nvswitch [ UP ]
rack-b-nvsw-01 nvswitch [ UP ]
"""
    monkeypatch.setattr(module, "_run_privileged", lambda *args, **kwargs: _completed(inventory))

    assert module._discover_switches("rack-a") == ["rack-a-nvsw-01", "rack-a-nvsw-02"]


def test_queries_complete_nvfwupd_inventory_read_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """A representative complete switch response produces BFX03-02 evidence."""
    module = _load_script()
    observed: dict[str, Any] = {}

    def fake_run(script: str, *args: str, timeout: int) -> subprocess.CompletedProcess[str]:
        """Record the helper invocation before returning representative inventory."""
        observed.update(script=script, args=args, timeout=timeout)
        return _completed(json.dumps(COMPLETE_INVENTORY))

    monkeypatch.setattr(module, "_run_privileged", fake_run)

    tray = module._query_tray("rack-a-nvsw-01")

    assert tray["tray_id"] == "rack-a-nvsw-01"
    assert tray["firmware_version"] == "3.0.0"
    assert tray["firmware_versions"]["ASIC"] == "1.0.0"
    assert tray["firmware_versions"]["CPLD3"] == "6.0.0"
    assert observed["args"] == ("rack-a-nvsw-01",)
    assert observed["timeout"] == 120
    assert "show_version -j" in observed["script"]
    assert all(token not in observed["script"] for token in ("update_fw", "update_firmware", "activate_fw"))


def test_main_passes_with_direct_gb300_tray_evidence(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One inspected GB300 NVSwitch tray satisfies the suite's minimum."""
    module = _load_script()
    monkeypatch.setattr(module, "_discover_switches", lambda rack: ["rack-a-nvsw-01"])
    monkeypatch.setattr(
        module,
        "_query_tray",
        lambda host: {
            "tray_id": host,
            "firmware_version": "3.0.0",
            "firmware_versions": {"BMC": "3.0.0", "ASIC": "1.0.0"},
        },
    )
    monkeypatch.setattr(sys, "argv", ["query_switch_firmware.py", "--rack", "rack-a"])

    assert module.main() == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "platform": "gb300",
        "source": "nvfwupd show_version -j",
        "success": True,
        "trays": [
            {
                "tray_id": "rack-a-nvsw-01",
                "firmware_version": "3.0.0",
                "firmware_versions": {"BMC": "3.0.0", "ASIC": "1.0.0"},
            }
        ],
    }

    check = NvSwitchFirmwareCheck(config={"step_output": payload})
    check.run()
    assert check.passed
    assert "1 NV switch tray(s)" in check.message


def test_assumed_gb300_without_switch_inventory_fails(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Applicable GB300 hardware cannot skip or pass without tray evidence."""
    module = _load_script()
    monkeypatch.setattr(module, "_discover_switches", lambda rack: [])
    monkeypatch.setattr(sys, "argv", ["query_switch_firmware.py", "--rack", "rack-a"])

    assert module.main() == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert payload["trays"] == []
    assert payload["error_type"] == "firmware_inspection"
    assert "no NVSwitch trays discovered" in payload["error"]
    assert "skipped" not in payload


@pytest.mark.parametrize("limit", ["0", "9"])
def test_invalid_switch_limit_emits_failure_json(
    limit: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Out-of-range limits must preserve the provider JSON contract."""
    module = _load_script()
    monkeypatch.setattr(sys, "argv", ["query_switch_firmware.py", f"--limit={limit}"])
    monkeypatch.setattr(
        module,
        "_discover_switches",
        lambda rack: pytest.fail("discovery must not run when parsing fails"),
    )

    assert module.main() == 1
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert captured.err == ""
    assert payload["success"] is False
    assert payload["trays"] == []
    assert "must be between 1 and 8" in payload["error"]


def test_comma_separated_switch_settings_bypass_discovery(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Explicit YAML-rendered targets are normalized without BCM discovery."""
    module = _load_script()
    monkeypatch.setattr(
        sys,
        "argv",
        ["query_switch_firmware.py", "--switch-hosts=rack-a-nvsw-01,rack-a-nvsw-02", "--limit=2"],
    )
    monkeypatch.setattr(
        module,
        "_discover_switches",
        lambda rack: pytest.fail("explicit switch hosts must bypass discovery"),
    )
    monkeypatch.setattr(
        module,
        "_query_tray",
        lambda host: {"tray_id": host, "firmware_version": "1.0", "firmware_versions": {"BMC": "1.0"}},
    )

    assert module.main() == 0
    payload = json.loads(capsys.readouterr().out)

    assert [tray["tray_id"] for tray in payload["trays"]] == ["rack-a-nvsw-01", "rack-a-nvsw-02"]


def test_incomplete_nvfwupd_device_preserves_failing_tray_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing component version retains the tray identity but cannot PASS."""
    module = _load_script()
    incomplete = {
        "Error Code": 0,
        "Firmware Devices": [
            {"AP Name": "BMC", "Sys Version": "3.0.0"},
            {"AP Name": "ASIC", "Sys Version": ""},
        ],
    }
    monkeypatch.setattr(
        module,
        "_run_privileged",
        lambda *args, **kwargs: _completed(json.dumps(incomplete)),
    )

    tray = module._query_tray("rack-a-nvsw-01")

    assert tray == {
        "tray_id": "rack-a-nvsw-01",
        "firmware_version": "",
        "firmware_versions": {"BMC": "3.0.0", "ASIC": ""},
    }
    check = NvSwitchFirmwareCheck(config={"step_output": {"success": True, "trays": [tray]}})
    check.run()
    assert not check.passed
    assert "missing firmware_version" in check.message


def test_nvfwupd_device_without_a_name_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unnamed component cannot be represented in the component inventory."""
    module = _load_script()
    malformed = {"Error Code": 0, "Firmware Devices": [{"AP Name": "", "Sys Version": "1.2.3"}]}
    monkeypatch.setattr(
        module,
        "_run_privileged",
        lambda *args, **kwargs: _completed(json.dumps(malformed)),
    )

    with pytest.raises(module.InspectionError, match="without a name"):
        module._query_tray("rack-a-nvsw-01")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("AP Name", 1, "without a name"),
        ("Sys Version", 1, "malformed firmware version"),
    ],
)
def test_non_string_nvfwupd_fields_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: int,
    message: str,
) -> None:
    """Numeric inventory fields cannot be coerced into firmware evidence."""
    module = _load_script()
    device = {"AP Name": "BMC", "Sys Version": "1.2.3"}
    device[field] = value
    malformed = {"Error Code": 0, "Firmware Devices": [device]}
    monkeypatch.setattr(
        module,
        "_run_privileged",
        lambda *args, **kwargs: _completed(json.dumps(malformed)),
    )

    with pytest.raises(module.InspectionError, match=message):
        module._query_tray("rack-a-nvsw-01")


def test_privileged_failure_does_not_leak_stderr(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """BMC credentials or raw command diagnostics never enter provider JSON."""
    module = _load_script()
    monkeypatch.setattr(module, "_discover_switches", lambda rack: ["rack-a-nvsw-01"])
    monkeypatch.setattr(
        module,
        "_run_privileged",
        lambda *args, **kwargs: _completed("", returncode=1, stderr="password=do-not-print"),
    )
    monkeypatch.setattr(sys, "argv", ["query_switch_firmware.py", "--rack", "rack-a"])

    assert module.main() == 1

    output = capsys.readouterr().out
    assert "do-not-print" not in output
    assert "password=" not in output
