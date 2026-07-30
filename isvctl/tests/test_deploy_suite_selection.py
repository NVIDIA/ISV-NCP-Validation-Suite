# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for deploy suite selection and its option parsing.

Every case here is rejected before the archive is built, so none of them reach
SSH.
"""

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

import isvctl.cli.deploy as deploy_cli

runner = CliRunner()

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def _write_catalog(root: Path) -> Path:
    """Write one platform suite and one plain suite; return the plain suite."""
    suites = root / "suites"
    suites.mkdir(parents=True)
    (suites / "k8s.yaml").write_text("tests:\n  capability: kubernetes\n  validations: {}\n", encoding="utf-8")
    plain = suites / "storage.yaml"
    plain.write_text("tests:\n  validations: {}\n", encoding="utf-8")
    return plain


def test_unknown_option_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """An option deploy does not have fails here instead of reaching pytest."""
    _write_catalog(tmp_path)
    monkeypatch.setattr(deploy_cli, "CONFIGS_ROOT", tmp_path)

    result = runner.invoke(deploy_cli.app, ["run", "1.2.3.4", "--suite", "storage", "--bogus", "x"])

    # Typer forces rich styling under GITHUB_ACTIONS, which splices escape
    # codes into the middle of the reported option name.
    output = _ANSI_ESCAPE.sub("", result.output)

    assert result.exit_code != 0, output
    assert "No such option" in output
    assert "--bogus" in output


def test_suite_cannot_be_combined_with_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Two ways of naming the same thing would silently disagree."""
    plain = _write_catalog(tmp_path)
    monkeypatch.setattr(deploy_cli, "CONFIGS_ROOT", tmp_path)

    result = runner.invoke(deploy_cli.app, ["run", "1.2.3.4", "--suite", "storage", "-f", str(plain)])

    assert result.exit_code == 1, result.output
    assert "--suite cannot be combined with --config/-f." in result.output


def test_unknown_suite_lists_the_available_ones(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A typo names the catalog it was looked up in."""
    _write_catalog(tmp_path)
    monkeypatch.setattr(deploy_cli, "CONFIGS_ROOT", tmp_path)

    result = runner.invoke(deploy_cli.app, ["run", "1.2.3.4", "--suite", "nosuch"])

    assert result.exit_code == 1, result.output
    assert "has no 'nosuch' suite" in result.output
    assert "storage" in result.output


def test_platform_suite_rejects_explicit_capability(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A platform suite already runs under the capability it declares."""
    _write_catalog(tmp_path)
    monkeypatch.setattr(deploy_cli, "CONFIGS_ROOT", tmp_path)

    result = runner.invoke(
        deploy_cli.app,
        ["run", "1.2.3.4", "--suite", "kubernetes", "--capability", "kubernetes"],
    )

    assert result.exit_code == 1, result.output
    assert "--capability cannot be used with platform suite 'kubernetes'" in result.output


def test_capability_uses_the_catalog_vocabulary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A capability no platform suite declares cannot gate anything."""
    _write_catalog(tmp_path)
    monkeypatch.setattr(deploy_cli, "CONFIGS_ROOT", tmp_path)

    result = runner.invoke(
        deploy_cli.app,
        ["run", "1.2.3.4", "--suite", "storage", "--capability", "compute"],
    )

    assert result.exit_code == 1, result.output
    assert "Unknown or non-declarable capability: compute" in result.output


def test_capability_option_reaches_the_remote_command() -> None:
    """The remote `test run` needs the context as an option, not just in reporting."""
    assert deploy_cli._capability_option("kubernetes") == "--capability kubernetes"
    assert deploy_cli._capability_option(None) == ""
