# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for deploy test-run reporting identity."""

from pathlib import Path

import pytest

import isvctl.cli.deploy as deploy_cli


def _write_catalog(root: Path) -> tuple[Path, Path]:
    """Write one platform suite and one plain suite."""
    suites = root / "suites"
    suites.mkdir(parents=True)
    platform = suites / "vm.yaml"
    platform.write_text("tests:\n  capability: vm\n  validations: {}\n", encoding="utf-8")
    plain = suites / "storage.yaml"
    plain.write_text("tests:\n  validations: {}\n", encoding="utf-8")
    return platform, plain


def test_platform_deploy_reports_its_suite_as_capability(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A platform-suite deploy records both axes instead of defaulting to core."""
    platform, _ = _write_catalog(tmp_path)
    monkeypatch.setattr(deploy_cli, "CONFIGS_ROOT", tmp_path)

    assert deploy_cli._reporting_suite_and_capability([platform]) == ("vm", "vm")


def test_plain_suite_deploy_reports_no_capability(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A plain-suite deploy remains a core run when it has no capability option."""
    _, plain = _write_catalog(tmp_path)
    monkeypatch.setattr(deploy_cli, "CONFIGS_ROOT", tmp_path)

    assert deploy_cli._reporting_suite_and_capability([plain]) == ("storage", None)
