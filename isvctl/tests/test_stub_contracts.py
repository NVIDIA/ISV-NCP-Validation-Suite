# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Contract test that detects stub / config drift.

**Canonical-YAML <-> stub CLI** - every ``--flag`` passed via ``args:`` in any
``tests/*.yaml`` or ``providers/**/*.yaml`` step must be accepted by the
argparse declaration of the stub it invokes. Catches the original
``create_user.py --create-access-key`` bug that kicked this work off.

Static analysis only: we parse stubs with ``ast`` and never execute them.

Note: an earlier iteration also cross-checked my-isv vs AWS argparse
signatures pair-wise. That was dropped because the two stub trees
deliberately diverge on platform-specific flag names (e.g. my-isv uses
``--credential-id`` / ``--image-id`` where AWS uses ``--access-key-id`` /
``--ami-id``). Any strict or subset comparison produces false positives on
legitimate design divergence, and the Canonical-YAML <-> stub check already
catches the actual class of drift we care about.
"""

from __future__ import annotations

import ast
import shlex
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGS_DIR = REPO_ROOT / "isvctl" / "configs"
STUBS_DIR = CONFIGS_DIR / "stubs"


# --------------------------------------------------------------------------
# Static argparse extraction
# --------------------------------------------------------------------------


def extract_argparse_flags(stub_path: Path) -> set[str]:
    """Return the set of ``--flag`` names the stub's argparse declares.

    Walks the AST for any call of the form ``<parser>.add_argument(...)``
    and collects every positional string argument that starts with ``--``.
    Handles aliased forms like ``add_argument("-r", "--region")``.
    """
    try:
        tree = ast.parse(stub_path.read_text())
    except SyntaxError as exc:  # pragma: no cover - stub should always parse
        pytest.fail(f"Cannot parse {stub_path}: {exc}")

    flags: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "add_argument"):
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value.startswith("--"):
                flags.add(arg.value)
    return flags


# --------------------------------------------------------------------------
# Canonical YAML args <-> stub CLI
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class StepArgCheck:
    """One YAML step's CLI contract to validate."""

    yaml_path: Path
    step_name: str
    stub_path: Path
    flags: tuple[str, ...]
    missing_reason: str | None = None

    def id(self) -> str:
        rel_yaml = self.yaml_path.relative_to(CONFIGS_DIR)
        return f"{rel_yaml}::{self.step_name}"


def _resolve_stub_path(yaml_path: Path, command: str) -> Path | None:
    """Extract the stub script path from a ``command:`` string and resolve it.

    ``command`` looks like ``"python3 ../stubs/my-isv/iam/create_user.py"`` or
    ``"../stubs/my-isv/k8s/setup.sh"``. Returns ``None`` when the command
    doesn't reference a Python stub we can statically analyse.
    """
    tokens = shlex.split(command)
    script = next(
        (t for t in tokens if t.endswith(".py") or t.endswith(".sh")),
        None,
    )
    if script is None:
        return None
    return (yaml_path.parent / script).resolve()


def _iter_steps(config: dict) -> Iterator[dict]:
    """Walk all step dicts inside the ``commands:`` section."""
    commands = config.get("commands") or {}
    if not isinstance(commands, dict):
        return
    for entry in commands.values():
        if not isinstance(entry, dict):
            continue
        steps = entry.get("steps") or []
        for step in steps:
            if isinstance(step, dict):
                yield step


def _yaml_flag_tokens(args: list[str]) -> list[str]:
    """Return the ``--flag`` tokens from a step's ``args:`` list.

    Jinja placeholders (``{{teardown_flag}}``) and plain values are ignored --
    only literal ``--flag`` strings are returned.
    """
    flags: list[str] = []
    for arg in args or []:
        if not isinstance(arg, str):
            continue
        if arg.startswith("--"):
            flags.append(arg)
    return flags


def _collect_yaml_checks() -> list[StepArgCheck]:
    """Walk every tests/ and providers/ YAML and collect one check per step."""
    checks: list[StepArgCheck] = []
    yaml_paths = sorted([*CONFIGS_DIR.glob("tests/*.yaml"), *CONFIGS_DIR.glob("providers/**/*.yaml")])
    for yaml_path in yaml_paths:
        try:
            doc = yaml.safe_load(yaml_path.read_text())
        except yaml.YAMLError as exc:  # pragma: no cover - yaml must parse
            pytest.fail(f"Cannot parse {yaml_path}: {exc}")
        if not isinstance(doc, dict):
            continue
        for step in _iter_steps(doc):
            if step.get("skip"):
                continue
            command = step.get("command")
            args = step.get("args")
            name = step.get("name") or "<unnamed>"
            if not isinstance(command, str) or not args:
                continue
            stub_path = _resolve_stub_path(yaml_path, command)
            flags = _yaml_flag_tokens(args)
            if stub_path is None:
                # Command didn't reference any .py/.sh script; nothing to check.
                continue
            if not stub_path.exists():
                # Path drift: the YAML's command points at a stub that doesn't
                # exist on disk. Emit a check so the test fails loudly instead
                # of silently skipping (which is what let drift slip through).
                checks.append(
                    StepArgCheck(
                        yaml_path=yaml_path,
                        step_name=name,
                        stub_path=stub_path,
                        flags=tuple(flags),
                        missing_reason=f"stub script not found at {stub_path}",
                    ),
                )
                continue
            if stub_path.suffix != ".py":
                # Shell scripts don't use argparse; skip them.
                continue
            if not flags:
                continue
            checks.append(
                StepArgCheck(
                    yaml_path=yaml_path,
                    step_name=name,
                    stub_path=stub_path,
                    flags=tuple(flags),
                ),
            )
    return checks


@pytest.mark.parametrize(
    "check",
    _collect_yaml_checks(),
    ids=lambda c: c.id() if isinstance(c, StepArgCheck) else "",
)
def test_yaml_step_args_match_stub_cli(check: StepArgCheck) -> None:
    """Every ``--flag`` a YAML step passes must be accepted by the stub's argparse."""
    if check.missing_reason is not None:
        pytest.fail(f"{check.id()}: {check.missing_reason}")
    accepted = extract_argparse_flags(check.stub_path)
    unknown = [flag for flag in check.flags if flag not in accepted]
    assert not unknown, (
        f"{check.id()} references unknown flags in "
        f"{check.stub_path.relative_to(REPO_ROOT)}:\n"
        f"  yaml passes:  {sorted(check.flags)}\n"
        f"  stub accepts: {sorted(accepted)}\n"
        f"  unknown:      {sorted(unknown)}"
    )
