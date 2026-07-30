# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for provider suite selection and capability parsing."""

from pathlib import Path

import pytest
from isvtest.core.resolution import DECLARABLE_CAPABILITIES, parse_validations
from pydantic import ValidationError

from isvctl.config.merger import merge_yaml_files
from isvctl.config.schema import RunConfig
from isvctl.config.suite_resolution import (
    SuiteResolutionError,
    parse_capability,
    resolve_suite,
    resolve_suite_name,
)

CONFIGS_ROOT = Path(__file__).resolve().parents[1] / "configs"


def _write_catalog(root: Path) -> None:
    """Write one platform suite, one plain suite, and provider imports."""
    suites = root / "suites"
    configs = root / "providers" / "acme" / "config"
    suites.mkdir(parents=True)
    configs.mkdir(parents=True)
    (suites / "k8s.yaml").write_text("tests:\n  capability: kubernetes\n  validations: {}\n")
    (suites / "storage.yaml").write_text("tests:\n  validations: {}\n")
    (configs / "eks.yaml").write_text("import: ../../../suites/k8s.yaml\ncommands: {}\n")
    (configs / "storage.yaml").write_text("import: ../../../suites/storage.yaml\ncommands: {}\n")


def test_one_suite_flag_resolves_platform_and_plain_suites(tmp_path: Path) -> None:
    """The same selector resolves both suite kinds by effective YAML identity."""
    _write_catalog(tmp_path)

    platform = resolve_suite("acme", "kubernetes", configs_root=tmp_path)
    plain = resolve_suite("acme", "storage", configs_root=tmp_path)

    assert platform.config_path.name == "eks.yaml"
    assert platform.platform == "kubernetes"
    assert plain.config_path.name == "storage.yaml"
    assert plain.platform is None


def test_capability_uses_catalog_vocabulary(tmp_path: Path) -> None:
    """An unknown capability is rejected while omitted context disables filtering."""
    _write_catalog(tmp_path)

    assert parse_capability(None, tmp_path) is None
    assert parse_capability("k8s", tmp_path) == "kubernetes"
    with pytest.raises(SuiteResolutionError, match="non-declarable capability: compute"):
        parse_capability("compute", tmp_path)
    with pytest.raises(SuiteResolutionError, match="single platform"):
        parse_capability("kubernetes,vm", tmp_path)


def test_platform_suites_reject_requires_and_unknown_platforms() -> None:
    """Platform placement is its obligation; it cannot declare check requirements."""
    validation = {"sample": {"checks": {"PlainCheck": {"requires": []}}}}

    with pytest.raises(ValidationError, match="requires is not allowed in platform suites"):
        RunConfig.model_validate({"tests": {"capability": "kubernetes", "validations": validation}})
    with pytest.raises(ValidationError, match=r"tests\.capability must be one of"):
        RunConfig.model_validate({"tests": {"capability": "compute", "validations": {}}})
    with pytest.raises(ValidationError, match=r"tests\.capability must be one of"):
        RunConfig.model_validate({"tests": {"capability": "", "validations": validation}})


def test_plain_suite_rejects_unknown_requires_vocabulary() -> None:
    """`test validate` catches a bad `requires` value, not just a run does."""
    validation = {"sample": {"checks": {"PlainCheck": {"requires": ["compute"]}}}}
    with pytest.raises(ValidationError, match="requires must be a list containing only"):
        RunConfig.model_validate({"tests": {"validations": validation}})


def test_plain_suite_rejects_duplicate_requires() -> None:
    """Duplicate requirements are rejected at schema-validation time."""
    validation = {"sample": {"checks": {"PlainCheck": {"requires": ["vm", "vm"]}}}}
    with pytest.raises(ValidationError, match="requires must not contain duplicates"):
        RunConfig.model_validate({"tests": {"validations": validation}})


def test_plain_suite_accepts_valid_requires() -> None:
    """A well-formed requires list passes schema validation."""
    validation = {"sample": {"checks": {"PlainCheck": {"requires": ["vm", "bare_metal"]}}}}
    RunConfig.model_validate({"tests": {"validations": validation}})


@pytest.mark.parametrize("provider", ["aws", "my-isv"])
def test_storage_cleanup_steps_have_explicit_capability_gates(provider: str) -> None:
    """Destructive storage cleanup runs only in the context that owns its resources.

    Both providers carry the same gates: my-isv is the scaffold ISVs copy, so a
    reference-only guarantee would teach the wrong lifecycle.
    """
    config_path = CONFIGS_ROOT / "providers" / provider / "config" / "storage.yaml"
    config = RunConfig.model_validate(merge_yaml_files([str(config_path)]))
    steps = {step.name: step for step in config.get_steps("storage")}

    assert steps["teardown_volume"].requires == ["vm", "bare_metal"]
    assert steps["teardown"].requires == ["vm", "bare_metal"]


def test_kubernetes_storage_groups_are_live_test_phase_probes() -> None:
    """Kubernetes storage groups must also run directly on an existing cluster."""
    config = RunConfig.model_validate(merge_yaml_files([str(CONFIGS_ROOT / "suites" / "storage.yaml")]))
    entries = parse_validations(config.tests.validations if config.tests else {})
    selected = [entry for entry in entries if entry.category in {"k8s_storage", "k8s_filesystem"}]

    assert {entry.category for entry in selected} == {"k8s_storage", "k8s_filesystem"}
    assert all(entry.step is None for entry in selected)


@pytest.mark.parametrize("capability", sorted(DECLARABLE_CAPABILITIES))
def test_my_isv_scaffold_covers_every_declarable_capability(capability: str) -> None:
    """Every capability an ISV can declare has a my-isv platform suite to copy.

    The UI emits `--suite <capability>` against the default provider, so a
    missing scaffold config turns a documented command into an error.
    """
    resolved = resolve_suite("my-isv", capability, configs_root=CONFIGS_ROOT)
    assert resolved.platform == capability


def test_suite_name_survives_every_entry_path(tmp_path: Path) -> None:
    """A run's suite must be recoverable from the configs, not just from --suite.

    `-f lab.yaml -f commands.yaml -f suites/k8s.yaml` is a documented entry
    path, and there the first config is not the suite - taking its stem would
    record the run against "lab".
    """
    _write_catalog(tmp_path)
    configs = tmp_path / "providers" / "acme" / "config"
    (configs / "lab.yaml").write_text("context: {}\n")

    assert resolve_suite_name([configs / "eks.yaml"], tmp_path) == "kubernetes"
    assert resolve_suite_name([configs / "storage.yaml"], tmp_path) == "storage"
    assert resolve_suite_name([configs / "lab.yaml", configs / "eks.yaml"], tmp_path) == "kubernetes"
    assert resolve_suite_name([tmp_path / "suites" / "k8s.yaml"], tmp_path) == "kubernetes"


def test_ad_hoc_config_falls_back_to_its_own_stem(tmp_path: Path) -> None:
    """An unrecognized config still labels its run rather than recording nothing."""
    _write_catalog(tmp_path)
    ad_hoc = tmp_path / "one-off.yaml"
    ad_hoc.write_text("commands: {}\n")

    assert resolve_suite_name([ad_hoc], tmp_path) == "one_off"
    assert resolve_suite_name([], tmp_path) is None
