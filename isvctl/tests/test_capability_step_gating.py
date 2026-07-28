# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Capability gating must leave every provider config internally consistent.

Running a plain suite under one capability context skips two kinds of step:
those carrying an explicit ``requires:``, and those whose bound validations are
all requirement-filtered. Either way the step produces no output, so any step
that survives the gate must not depend on a skipped step's output without an
explicit ``default(...)`` - otherwise the orchestrator raises
``MissingStepRefError`` and silently abandons the cleanup that step owned.

This walks every provider config rather than the three that regressed, so a new
suite inherits the guarantee instead of re-discovering it.
"""

import re
from pathlib import Path
from typing import Any

import pytest
from isvtest.core.resolution import (
    DECLARABLE_CAPABILITIES,
    ValidationEntry,
    parse_validations,
)

from isvctl.cli.test import CORE_REQUIREMENT_CONTEXT
from isvctl.config.merger import merge_yaml_files
from isvctl.config.schema import RunConfig
from isvctl.orchestrator.loop import _apply_capability_step_gates

CONFIGS_ROOT = Path(__file__).resolve().parents[1] / "configs"
PROVIDERS_ROOT = CONFIGS_ROOT / "providers"
# Every context a plain suite can be run under, including the core-only default
# that `--suite NAME` (no `--capability`) selects.
CONTEXTS = (CORE_REQUIREMENT_CONTEXT, *sorted(DECLARABLE_CAPABILITIES))
STEP_REFERENCE = re.compile(r"steps\.([A-Za-z0-9_]+)")
JINJA_EXPRESSION = re.compile(r"\{\{.*?\}\}", re.DOTALL)


def _plain_suite_configs() -> list[tuple[str, Path]]:
    """Return (provider, config path) for every plain-suite provider config."""
    configs: list[tuple[str, Path]] = []
    # Discovered rather than listed so a new provider inherits the guarantee.
    for config_dir in sorted(PROVIDERS_ROOT.glob("*/config")):
        provider = config_dir.parent.name
        for path in sorted(config_dir.glob("*.yaml")):
            config = RunConfig.model_validate(merge_yaml_files([str(path)]))
            # Platform suites carry no `requires:` on their checks, so nothing
            # is ever gated inside them.
            if config.tests and config.tests.capability:
                continue
            configs.append((provider, path))
    return configs


def _gated_step_names(steps: list[Any], entries: list[ValidationEntry], context: str) -> set[str]:
    """Return the steps `_apply_capability_step_gates` skips in a context.

    Asks the real gate rather than restating its rules, so a change to what
    gets skipped is exercised here instead of silently passing against a copy.
    """
    gated = _apply_capability_step_gates(steps, entries, context)
    return {after.name for before, after in zip(steps, gated, strict=True) if after.skip and not before.skip}


def _unguarded_references(value: Any) -> set[str]:
    """Return step names referenced without a `default(...)` fallback.

    Scoped per `{{ ... }}`: one guarded expression does not vouch for its
    neighbours in the same string.
    """
    referenced: set[str] = set()
    if isinstance(value, str):
        for expression in JINJA_EXPRESSION.findall(value):
            if "default(" not in expression:
                referenced |= set(STEP_REFERENCE.findall(expression))
        return referenced
    if isinstance(value, dict):
        for item in value.values():
            referenced |= _unguarded_references(item)
    elif isinstance(value, list):
        for item in value:
            referenced |= _unguarded_references(item)
    return referenced


@pytest.mark.parametrize(("provider", "config_path"), _plain_suite_configs(), ids=lambda v: getattr(v, "stem", v))
@pytest.mark.parametrize("context", CONTEXTS)
def test_surviving_steps_never_depend_on_gated_steps(provider: str, config_path: Path, context: str) -> None:
    """No step that survives capability gating may read a gated step's output."""
    config = RunConfig.model_validate(merge_yaml_files([str(config_path)]))
    entries = parse_validations(config.tests.validations if config.tests else {})

    violations: list[str] = []
    for platform_key in config.commands:
        steps = config.get_steps(platform_key)
        gated = _gated_step_names(steps, entries, context)
        if not gated:
            continue
        for step in steps:
            if step.name in gated:
                continue
            dangling = _unguarded_references(step.model_dump()) & gated
            for missing in sorted(dangling):
                violations.append(f"step '{step.name}' reads skipped step '{missing}'")

    assert not violations, (
        f"{provider}/{config_path.name} under context '{context}': "
        + "; ".join(violations)
        + ". Gate the step with `requires:` or give the reference a `default(...)`."
    )


class TestUnguardedReferences:
    """The guard is per `{{ ... }}`, not per string."""

    def test_guarded_reference_is_ignored(self) -> None:
        assert _unguarded_references("{{ steps.setup.id | default('') }}") == set()

    def test_bare_reference_is_reported(self) -> None:
        assert _unguarded_references("{{ steps.setup.id }}") == {"setup"}

    def test_a_guarded_expression_does_not_cover_its_neighbour(self) -> None:
        """The bug this guards: one `default(` used to blank the whole string."""
        value = "{{ steps.a.id | default('') }} {{ steps.b.id }}"
        assert _unguarded_references(value) == {"b"}

    def test_reference_outside_an_expression_is_not_a_dependency(self) -> None:
        assert _unguarded_references("see steps.setup in the docs") == set()

    def test_nested_structures_are_walked(self) -> None:
        value = {"args": ["{{ steps.a.id }}", {"k": "{{ steps.b.id | default('') }}"}]}
        assert _unguarded_references(value) == {"a"}
