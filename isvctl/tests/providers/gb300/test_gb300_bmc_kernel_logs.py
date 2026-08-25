# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for direct GB300 BMC log inspection (BFX03-03)."""

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
from isvtest.validations.breakfix import BmcKernelLogCheck

from isvctl.config.merger import merge_yaml_files
from isvctl.config.schema import RunConfig
from isvctl.orchestrator.context import Context
from isvctl.orchestrator.step_executor import StepExecutor

ISVCTL_ROOT = Path(__file__).resolve().parents[3]
GB300_ROOT = ISVCTL_ROOT / "configs" / "providers" / "gb300"
SCRIPT_PATH = GB300_ROOT / "scripts" / "breakfix" / "query_bmc_kernel_logs.py"
CONFIG_PATH = GB300_ROOT / "config" / "bare_metal.yaml"


def _load_script() -> ModuleType:
    """Load the provider script as an isolated module."""
    spec = importlib.util.spec_from_file_location("test_gb300_bmc_kernel_logs_script", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _completed(stdout: str, *, returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess[str]:
    """Build a subprocess result for privileged-helper mocks."""
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)


def _journal_evidence(*, message_count: int = 3) -> str:
    """Build representative normalized journal evidence."""
    return json.dumps(
        {
            "log_source": "/redfish/v1/Managers/BMC_0/LogServices/Journal/Entries",
            "message_count": message_count,
        }
    )


def test_config_wires_the_read_only_bmc_query() -> None:
    """The GB300 bare-metal config binds BFX03-03's read-only query step."""
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    steps = config["commands"]["bare_metal"]["steps"]
    step = next(item for item in steps if item["name"] == "query_bmc_kernel_logs")

    assert step == {
        "name": "query_bmc_kernel_logs",
        "phase": "test",
        "continue_on_failure": True,
        "command": "python ../scripts/breakfix/query_bmc_kernel_logs.py",
        "args": [
            "--node-host={{ gb300_node_host | default('', true) }}",
            "--ca-cert={{ gb300_bmc_ca_cert | default('', true) }}",
        ],
        "timeout": 120,
    }
    assert config["tests"]["settings"]["gb300_node_host"] == ""
    assert config["tests"]["settings"]["gb300_bmc_ca_cert"] == ""


def test_bmc_inputs_render_from_test_settings() -> None:
    """The GB300 target and trust path are ordinary YAML settings."""
    merged = merge_yaml_files(
        [CONFIG_PATH],
        set_values=[
            "tests.settings.gb300_node_host=gb300-node-01",
            "tests.settings.gb300_bmc_ca_cert=/trusted/bmc-ca.pem",
        ],
    )
    config = RunConfig.model_validate(merged)
    step = next(item for item in config.commands["bare_metal"].steps if item.name == "query_bmc_kernel_logs")

    assert StepExecutor()._render_args(step.args, Context(config)) == [
        "--node-host=gb300-node-01",
        "--ca-cert=/trusted/bmc-ca.pem",
    ]


def test_privileged_helper_contains_only_read_operations(monkeypatch: pytest.MonkeyPatch) -> None:
    """The GB300 helper performs BCM reads and Redfish GETs only."""
    module = _load_script()
    observed: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        observed.update(command=command, kwargs=kwargs)
        return _completed(_journal_evidence())

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    module._run_privileged("gb300-node-01", "/etc/ssl/certs/bmc-ca.pem")

    script = observed["kwargs"]["input"]
    assert observed["command"] == [
        "sudo",
        "-n",
        "bash",
        "-s",
        "--",
        "gb300-node-01",
        "/etc/ssl/certs/bmc-ca.pem",
    ]
    assert "--insecure" not in script
    assert '--cacert "$bmc_ca_cert"' in script
    assert '[ ! -f "$bmc_ca_cert" ] || [ ! -r "$bmc_ca_cert" ]' in script
    assert 'get_redfish "/redfish/v1/Managers"' in script
    assert 'service_id" != "Journal"' in script
    assert "*bmc*journal*" in script
    assert "LogServices/EventLog" not in script
    assert "/redfish/v1/Systems" not in script
    assert "--request GET" not in script
    assert all(
        token not in script for token in ("-X POST", "-X PATCH", "-X DELETE", "clearlog", "CollectDiagnosticData")
    )


def test_representative_log_produces_passing_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    """Representative Manager Journal messages satisfy BFX03-03."""
    module = _load_script()
    monkeypatch.setattr(module, "_run_privileged", lambda host, ca_cert: _completed(_journal_evidence()))

    host = module._query_host("gb300-node-01", "/trusted/bmc-ca.pem")

    assert host == {
        "host_id": "gb300-node-01",
        "kernel_log_available": True,
        "message_count": 3,
        "log_source": "/redfish/v1/Managers/BMC_0/LogServices/Journal/Entries",
    }
    check = BmcKernelLogCheck(config={"step_output": {"success": True, "hosts": [host]}})
    check.run()
    assert check.passed


def test_empty_log_cannot_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    """A reachable BMC without actual messages is not positive evidence."""
    module = _load_script()
    monkeypatch.setattr(
        module,
        "_run_privileged",
        lambda host, ca_cert: _completed(_journal_evidence(message_count=0)),
    )

    with pytest.raises(module.InspectionError, match="no log messages"):
        module._query_host("gb300-node-01")


def test_main_fails_when_target_is_not_configured(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An applicable GB300 run fails rather than skipping without a target."""
    module = _load_script()
    monkeypatch.setattr(sys, "argv", [SCRIPT_PATH.name])

    assert module.main() == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert payload["hosts"] == []
    assert payload["error"] == "GB300 node host is required"
    assert "skipped" not in payload


def test_query_failure_does_not_leak_stderr(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Credentials and raw command diagnostics never enter provider JSON."""
    module = _load_script()
    monkeypatch.setattr(
        module,
        "_run_privileged",
        lambda host, ca_cert: _completed("", returncode=23, stderr="password=do-not-print"),
    )
    monkeypatch.setattr(sys, "argv", [SCRIPT_PATH.name, "--node-host=gb300-node-01"])

    assert module.main() == 1
    output = capsys.readouterr().out
    assert "do-not-print" not in output
    assert "password=" not in output
    assert json.loads(output)["error"] == "unable to retrieve a non-empty GB300 BMC Journal log"


def test_invalid_arguments_emit_failure_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Argument errors must preserve the provider JSON contract."""
    module = _load_script()
    monkeypatch.setattr(sys, "argv", [SCRIPT_PATH.name, "--unknown-option"])
    monkeypatch.setattr(
        module,
        "_query_host",
        lambda *args: pytest.fail("the BMC must not be queried when parsing fails"),
    )

    assert module.main() == 1
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert captured.err == ""
    assert payload["success"] is False
    assert payload["hosts"] == []
    assert "unrecognized arguments" in payload["error"]


def test_invalid_hostname_is_rejected_before_privileged_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shell metacharacters cannot enter the fixed privileged helper."""
    module = _load_script()
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: pytest.fail("must not run"))

    with pytest.raises(module.InspectionError, match="invalid GB300 node hostname"):
        module._run_privileged("node;reboot")
