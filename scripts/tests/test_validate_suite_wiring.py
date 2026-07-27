# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for validate_suite_wiring.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "validate_suite_wiring", Path(__file__).resolve().parent.parent / "validate_suite_wiring.py"
)
assert _spec and _spec.loader
validate_suite_wiring = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validate_suite_wiring)


def test_wiring_errors_flags_missing_metadata(tmp_path: Path) -> None:
    """Missing test_id or labels on a wired check is reported with context."""
    suite = tmp_path / "demo.yaml"
    suite.write_text(
        """\
tests:
  validations:
    example:
      checks:
        GoodCheck:
          test_id: "SEC01-01"
          labels: ["demo", "security"]
          requires: []
        BadCheck:
          labels: ["demo", "security"]
          requires: []
        AlsoBad:
          test_id: "N/A"
          requires: []
"""
    )
    errors = validate_suite_wiring.wiring_errors(tmp_path)
    assert any("demo.yaml:" in err and "BadCheck" in err and "missing test_id" in err for err in errors)
    assert any("demo.yaml:" in err and "AlsoBad" in err and "missing labels" in err for err in errors)
    assert not any("GoodCheck" in err for err in errors)


def test_wiring_errors_rejects_scalar_labels(tmp_path: Path) -> None:
    """Scalar ``labels`` values must fail validation; only lists are accepted."""
    suite = tmp_path / "demo.yaml"
    suite.write_text(
        """\
tests:
  platform: kubernetes
  validations:
    example:
      checks:
        BadCheck:
          test_id: "N/A"
          labels: kubernetes
"""
    )
    errors = validate_suite_wiring.wiring_errors(tmp_path)
    assert any("BadCheck" in err and "missing labels" in err for err in errors)


def test_wiring_errors_require_canonical_suite_label(tmp_path: Path) -> None:
    """Checks in known suite files must include that suite's label."""
    suite = tmp_path / "k8s.yaml"
    suite.write_text(
        """\
tests:
  platform: kubernetes
  validations:
    example:
      checks:
        MissingSuiteLabel:
          test_id: "K8S01-01"
          labels: ["gpu"]
        GoodCheck:
          test_id: "K8S01-02"
          labels: ["gpu", "kubernetes"]
"""
    )
    errors = validate_suite_wiring.wiring_errors(tmp_path)
    assert any("MissingSuiteLabel" in err and "missing suite label 'kubernetes'" in err for err in errors)
    assert not any("GoodCheck" in err for err in errors)


def test_wiring_errors_reports_yaml_parse_failures(tmp_path: Path) -> None:
    """Malformed suite YAML surfaces as a validation error instead of being skipped."""
    suite = tmp_path / "broken.yaml"
    suite.write_text("tests:\n  validations:\n    bad: [:\n")
    errors = validate_suite_wiring.wiring_errors(tmp_path)
    assert len(errors) == 1
    assert "broken.yaml" in errors[0]
    assert "failed to read/parse" in errors[0]


def test_find_check_line_numbers_supports_list_form() -> None:
    """List-form wiring reports each repeated check at its own line."""
    lines = """
tests:
  validations:
    pools:
      - K8sNodePoolCheck:
          test_id: "K8S06-01"
          labels: ["kubernetes"]
      - K8sNodePoolCheck:
          labels: ["kubernetes"]
""".splitlines()
    assert validate_suite_wiring.find_check_line_numbers(lines, "pools", "K8sNodePoolCheck") == [5, 8]


def test_repo_suites_declare_test_id_and_labels() -> None:
    """Guardrail: every check in isvctl/configs/suites declares wiring metadata."""
    errors = validate_suite_wiring.wiring_errors()
    assert not errors, "suite wiring validation failed:\n  " + "\n  ".join(errors)


def test_plain_suite_requires_are_explicit_and_valid(tmp_path: Path) -> None:
    """Plain suites require an allowed list, including an explicit empty list."""
    (tmp_path / "demo.yaml").write_text(
        """\
tests:
  validations:
    sample:
      checks:
        MissingCheck:
          test_id: "N/A"
          labels: ["demo"]
        InvalidCheck:
          test_id: "N/A"
          labels: ["demo"]
          requires: [foundational]
"""
    )

    errors = validate_suite_wiring.wiring_errors(tmp_path)
    assert any("MissingCheck" in error and "missing requires" in error for error in errors)
    assert any("InvalidCheck" in error and "requires must be a list containing only" in error for error in errors)


def test_wiring_errors_rejects_plain_suite_named_after_capability(tmp_path: Path) -> None:
    """A plain suite file named like a declarable capability is a namespace collision."""
    (tmp_path / "kubernetes.yaml").write_text(
        """\
tests:
  validations:
    sample:
      checks:
        SomeCheck:
          test_id: "N/A"
          labels: ["demo"]
          requires: []
"""
    )

    errors = validate_suite_wiring.wiring_errors(tmp_path)
    assert any("kubernetes" in error and "collides with a declarable capability" in error for error in errors)


def test_wiring_errors_flags_requires_with_no_platform_suite(tmp_path: Path) -> None:
    """A `requires` naming a capability that has no platform suite is unreachable."""
    (tmp_path / "vm.yaml").write_text(
        """\
tests:
  platform: vm
  validations:
    example:
      checks:
        VmCheck:
          test_id: "N/A"
          labels: ["vm"]
"""
    )
    (tmp_path / "demo.yaml").write_text(
        """\
tests:
  validations:
    example:
      checks:
        DeadCheck:
          test_id: "N/A"
          labels: ["demo"]
          requires: [slurm]
"""
    )

    errors = validate_suite_wiring.wiring_errors(tmp_path)
    assert any("DeadCheck" in error and "slurm" in error and "no platform suite" in error for error in errors)


def test_wiring_errors_allows_platform_suite_named_after_capability(tmp_path: Path) -> None:
    """The kubernetes *platform* suite (declares tests.platform) is not a collision."""
    (tmp_path / "k8s.yaml").write_text(
        """\
tests:
  platform: kubernetes
  validations:
    sample:
      checks:
        SomeCheck:
          test_id: "N/A"
          labels: ["kubernetes"]
"""
    )

    errors = validate_suite_wiring.wiring_errors(tmp_path)
    assert not any("collides with a declarable capability" in error for error in errors)
