# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the shared BFX04-01 node-health-agent reference."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

from isvctl.config.merger import merge_yaml_files
from isvctl.config.schema import RunConfig
from isvctl.orchestrator.context import Context
from isvctl.orchestrator.step_executor import StepExecutor

ISVCTL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ISVCTL_ROOT / "configs" / "providers" / "shared" / "breakfix" / "query_node_health_agents.py"
BARE_METAL_SUITE = ISVCTL_ROOT / "configs" / "suites" / "bare_metal.yaml"
NICO_CONFIG = ISVCTL_ROOT / "configs" / "providers" / "nico" / "config" / "bare_metal.yaml"


def _load_script() -> ModuleType:
    """Load the shared node-health-agent script as a module for direct testing."""
    spec = importlib.util.spec_from_file_location("test_shared_node_health_agents_script", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _ssh_stub(
    states_by_node: dict[str, str],
    calls: list[list[str]] | None = None,
) -> object:
    """Return a ``subprocess.run`` stub answering per-node ``systemctl`` probes."""

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if calls is not None:
            calls.append(command)
        node = command[-2]
        return subprocess.CompletedProcess(command, 0, stdout=states_by_node[node], stderr="")

    return fake_run


def _states(*active_units: str) -> str:
    """Return ``systemctl is-active`` output marking ``active_units`` active."""
    units = ("fleetintd", "gpud", "nvsentinel", "gpu-health-monitor")
    return "".join(f"{'active' if unit in active_units else 'inactive'}\n" for unit in units)


def test_bare_metal_suite_declares_the_provider_neutral_validation() -> None:
    """Keep BFX04-01 in the bare-metal suite while providers own executable steps."""
    config = yaml.safe_load(BARE_METAL_SUITE.read_text())
    validation = config["tests"]["validations"]["node_health_agents"]

    assert validation["step"] == "query_node_health_agents"
    assert validation["checks"]["NodeHealthAgentCheck"]["test_id"] == "BFX04-01"
    assert validation["checks"]["NodeHealthAgentCheck"]["labels"] == ["bare_metal", "breakfix"]


def test_nico_provider_wires_the_shared_reference() -> None:
    """The NICo bare-metal provider must execute the shared reference."""
    config = yaml.safe_load(NICO_CONFIG.read_text())
    step = next(
        item for item in config["commands"]["bare_metal"]["steps"] if item["name"] == "query_node_health_agents"
    )

    assert step["command"] == "python ../../shared/breakfix/query_node_health_agents.py"
    assert step["phase"] == "test"
    assert step["timeout"] == 300
    assert step["requires_available_validations"] == ["NodeHealthAgentCheck"]
    assert step["args"] == ["--nodes={{health_agent_nodes}}"]
    assert config["tests"]["settings"]["health_agent_nodes"] == "{{env.NICO_HEALTH_AGENT_NODES | default('', true)}}"


def test_nodes_render_empty_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unset target list renders empty so the provider can skip safely."""
    monkeypatch.delenv("NICO_HEALTH_AGENT_NODES", raising=False)
    config = RunConfig.model_validate(merge_yaml_files([NICO_CONFIG]))
    step = next(item for item in config.commands["bare_metal"].steps if item.name == "query_node_health_agents")

    assert StepExecutor()._render_args(step.args, Context(config)) == ["--nodes="]


def test_nodes_accept_configured_environment_targets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configured GPU nodes are rendered into the provider command."""
    monkeypatch.setenv("NICO_HEALTH_AGENT_NODES", "gpu-01,gpu-02")
    config = RunConfig.model_validate(merge_yaml_files([NICO_CONFIG]))
    step = next(item for item in config.commands["bare_metal"].steps if item.name == "query_node_health_agents")

    assert StepExecutor()._render_args(step.args, Context(config)) == ["--nodes=gpu-01,gpu-02"]


def test_unconfigured_nodes_skip_before_any_ssh(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """With nothing configured the step must skip rather than claim a pass."""
    module = _load_script()

    def refuse(*_: object, **__: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError("no SSH probe may run without configured nodes")

    monkeypatch.setattr(module.subprocess, "run", refuse)
    monkeypatch.setattr(sys, "argv", [SCRIPT.name, "--nodes="])

    assert module.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "success": True,
        "platform": "bare_metal",
        "test_name": "query_node_health_agents",
        "skipped": True,
        "skip_reason": "No GPU nodes configured for health-agent inspection",
        "agents_observable": False,
        "agents": [],
    }


@pytest.mark.parametrize("unit", ["fleetintd", "gpud", "nvsentinel", "gpu-health-monitor"])
def test_any_supported_agent_unit_covers_its_node(unit: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Either accepted agent, under any of its unit names, proves coverage."""
    module = _load_script()
    monkeypatch.setattr(module.subprocess, "run", _ssh_stub({"gpu-01": _states(unit)}))

    result = module._query(["gpu-01"])

    assert result["agents_observable"] is True
    assert result["agents"] == [{"node_id": "gpu-01", "agent_name": unit, "running": True}]


def test_node_without_an_active_agent_is_reported_as_not_running(monkeypatch: pytest.MonkeyPatch) -> None:
    """An inactive fleet cannot produce a false pass."""
    module = _load_script()
    monkeypatch.setattr(module.subprocess, "run", _ssh_stub({"gpu-01": _states()}))

    result = module._query(["gpu-01"])

    assert result["agents"] == [{"node_id": "gpu-01", "agent_name": "", "running": False}]


def test_evidence_stays_aligned_with_its_node(monkeypatch: pytest.MonkeyPatch) -> None:
    """Concurrent probes must not misattribute one node's agent to another."""
    module = _load_script()
    states = {"gpu-01": _states("gpud"), "gpu-02": _states(), "gpu-03": _states("nvsentinel")}
    monkeypatch.setattr(module.subprocess, "run", _ssh_stub(states))

    result = module._query(["gpu-01", "gpu-02", "gpu-03"])

    assert result["agents"] == [
        {"node_id": "gpu-01", "agent_name": "gpud", "running": True},
        {"node_id": "gpu-02", "agent_name": "", "running": False},
        {"node_id": "gpu-03", "agent_name": "nvsentinel", "running": True},
    ]


def test_repeated_nodes_are_probed_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """A duplicated target must not inflate the reported node count."""
    module = _load_script()
    calls: list[list[str]] = []
    monkeypatch.setattr(module.subprocess, "run", _ssh_stub({"gpu-01": _states("gpud")}, calls))

    result = module._query(module._parse_nodes("gpu-01, gpu-01"))

    assert len(calls) == 1
    assert [agent["node_id"] for agent in result["agents"]] == ["gpu-01"]


def test_probe_ends_ssh_options_before_the_node(monkeypatch: pytest.MonkeyPatch) -> None:
    """``--`` must precede the host so a target can never be read as an option."""
    module = _load_script()
    calls: list[list[str]] = []
    monkeypatch.setattr(module.subprocess, "run", _ssh_stub({"gpu-01": _states("gpud")}, calls))

    module._query(["gpu-01"])

    assert calls[0][:1] == ["ssh"]
    assert calls[0][-3:] == [
        "--",
        "gpu-01",
        "systemctl is-active fleetintd gpud nvsentinel gpu-health-monitor 2>/dev/null || true",
    ]
    assert "BatchMode=yes" in calls[0]


@pytest.mark.parametrize("value", ["-oProxyCommand=x", "gpu-01;reboot", "$(reboot)", "root@gpu-01"])
def test_unsafe_node_names_are_rejected(value: str) -> None:
    """Node input cannot smuggle SSH options or remote shell syntax."""
    module = _load_script()

    with pytest.raises(module.NodeHealthQueryError, match="Invalid bare-metal node name"):
        module._parse_nodes(value)


def test_transport_failure_is_reported_without_leaking_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """SSH failures fail the step without copying host output into the payload."""
    module = _load_script()
    failure = subprocess.CompletedProcess([], 255, stdout="private inventory", stderr="private auth error")
    monkeypatch.setattr(module.subprocess, "run", lambda *_, **__: failure)
    monkeypatch.setattr(sys, "argv", [SCRIPT.name, "--nodes=gpu-01"])

    assert module.main() == 1
    output = capsys.readouterr().out
    assert "private" not in output
    payload = json.loads(output)
    assert payload["success"] is False
    assert payload["error_type"] == "node_health_query_failed"


def test_unreadable_node_never_becomes_a_not_running_record(monkeypatch: pytest.MonkeyPatch) -> None:
    """A node we could not reach must not be reported as lacking an agent.

    ``NodeHealthAgentCheck`` reads only ``running``, so emitting a record for an
    unreachable node would blame a missing agent for an access problem.
    """
    module = _load_script()
    states = {"gpu-01": _states("gpud")}

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        node = command[-2]
        if node not in states:
            return subprocess.CompletedProcess(command, 255, stdout="", stderr="no route to host")
        return subprocess.CompletedProcess(command, 0, stdout=states[node], stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    with pytest.raises(module.NodeHealthQueryError) as raised:
        module._query(["gpu-01", "gpu-99"])

    assert "gpu-99" in str(raised.value)


def test_every_unreadable_node_is_named(monkeypatch: pytest.MonkeyPatch) -> None:
    """One run must diagnose a fleet-wide access problem, not just its first node."""
    module = _load_script()
    unreachable = subprocess.CompletedProcess([], 255, stdout="", stderr="")
    monkeypatch.setattr(module.subprocess, "run", lambda *_, **__: unreachable)

    with pytest.raises(module.NodeHealthQueryError) as raised:
        module._query(["gpu-01", "gpu-02", "gpu-03"])

    assert str(raised.value) == "Health agent query failed for 3 node(s): gpu-01, gpu-02, gpu-03"


def test_unreadable_systemctl_output_fails_rather_than_passing(monkeypatch: pytest.MonkeyPatch) -> None:
    """A node without systemd yields no evidence, so it cannot be counted covered."""
    module = _load_script()
    monkeypatch.setattr(module.subprocess, "run", _ssh_stub({"gpu-01": ""}))

    with pytest.raises(module.NodeHealthQueryError, match="gpu-01"):
        module._query(["gpu-01"])

    assert module._probe("gpu-01") is None


def test_invalid_arguments_emit_failure_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Argument errors must preserve the provider JSON contract."""
    module = _load_script()
    monkeypatch.setattr(sys, "argv", [SCRIPT.name, "--unknown-option"])

    assert module.main() == 1
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert captured.err == ""
    assert payload["success"] is False
    assert "unrecognized arguments" in payload["error"]
