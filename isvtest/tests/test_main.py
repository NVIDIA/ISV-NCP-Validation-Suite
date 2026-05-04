# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Tests for isvtest.main module."""

from typing import Any

import pytest

import isvtest.main
from isvtest.main import _transform_validations_for_pytest


def test_dummy() -> None:
    """A simple dummy test that always passes."""
    assert True


def test_main_module_exists() -> None:
    """Test that the main module can be imported."""
    assert isvtest.main is not None


# ---------------------------------------------------------------------------
# _transform_validations_for_pytest
# ---------------------------------------------------------------------------


class TestTransformValidationsForPytest:
    """Tests for the validation transform that feeds pytest parametrization."""

    # Shared fixtures ---------------------------------------------------------

    @pytest.fixture()
    def step_outputs(self) -> dict[str, dict[str, Any]]:
        """Simulated step outputs keyed by step name."""
        return {
            "launch_instance": {"instance_id": "i-abc", "state": "running"},
            "describe_instance": {"instance_id": "i-abc", "state": "running"},
            "reboot_instance": {"instance_id": "i-abc", "state": "running"},
        }

    @pytest.fixture()
    def step_phases(self) -> dict[str, str]:
        """Mapping of step names to the phase they belong to."""
        return {
            "launch_instance": "setup",
            "describe_instance": "test",
            "reboot_instance": "test",
        }

    # Helpers -----------------------------------------------------------------

    @staticmethod
    def _keys(result: list[dict[str, Any]]) -> list[str]:
        """Extract the validation key from each entry."""
        return [next(iter(d)) for d in result]

    # Tests -------------------------------------------------------------------

    def test_unique_checks_keep_bare_name(
        self,
        step_outputs: dict[str, dict[str, Any]],
        step_phases: dict[str, str],
    ) -> None:
        """When each class name is unique, no suffix is added."""
        validations: dict[str, Any] = {
            "ssh": {
                "step": "describe_instance",
                "checks": {"ConnectivityCheck": {}, "OsCheck": {}},
            },
        }
        result = _transform_validations_for_pytest(validations, step_outputs, step_phases, "test")
        keys = self._keys(result)
        assert keys == ["ConnectivityCheck", "OsCheck"]

    def test_duplicate_checks_get_category_suffix(
        self,
        step_outputs: dict[str, dict[str, Any]],
        step_phases: dict[str, str],
    ) -> None:
        """Same class in multiple categories gets '-category' suffix."""
        validations: dict[str, Any] = {
            "instance_info": {
                "step": "describe_instance",
                "checks": {"InstanceStateCheck": {"expected_state": "running"}},
            },
            "reboot_state": {
                "step": "reboot_instance",
                "checks": {"InstanceStateCheck": {"expected_state": "running"}},
            },
        }
        result = _transform_validations_for_pytest(validations, step_outputs, step_phases, "test")
        keys = self._keys(result)
        assert "InstanceStateCheck-instance_info" in keys
        assert "InstanceStateCheck-reboot_state" in keys
        assert len(keys) == 2

    def test_duplicate_checks_preserve_params(
        self,
        step_outputs: dict[str, dict[str, Any]],
        step_phases: dict[str, str],
    ) -> None:
        """Qualified entries keep correct step_output and _category."""
        validations: dict[str, Any] = {
            "instance_info": {
                "step": "describe_instance",
                "checks": {"InstanceStateCheck": {"expected_state": "running"}},
            },
            "reboot_state": {
                "step": "reboot_instance",
                "checks": {"InstanceStateCheck": {"expected_state": "running"}},
            },
        }
        result = _transform_validations_for_pytest(validations, step_outputs, step_phases, "test")
        by_key = {next(iter(d)): next(iter(d.values())) for d in result}

        info = by_key["InstanceStateCheck-instance_info"]
        assert info["_category"] == "instance_info"
        assert info["step_output"] == step_outputs["describe_instance"]

        reboot = by_key["InstanceStateCheck-reboot_state"]
        assert reboot["_category"] == "reboot_state"
        assert reboot["step_output"] == step_outputs["reboot_instance"]

    def test_mixed_unique_and_duplicate(
        self,
        step_outputs: dict[str, dict[str, Any]],
        step_phases: dict[str, str],
    ) -> None:
        """Unique checks stay bare; only duplicates get the suffix."""
        validations: dict[str, Any] = {
            "ssh": {
                "step": "describe_instance",
                "checks": {"ConnectivityCheck": {}, "GpuCheck": {}},
            },
            "reboot_ssh": {
                "step": "reboot_instance",
                "checks": {"ConnectivityCheck": {}, "DriverCheck": {}},
            },
        }
        result = _transform_validations_for_pytest(validations, step_outputs, step_phases, "test")
        keys = self._keys(result)
        assert "ConnectivityCheck-ssh" in keys
        assert "ConnectivityCheck-reboot_ssh" in keys
        assert "GpuCheck" in keys
        assert "DriverCheck" in keys

    def test_phase_filtering_excludes_other_phases(
        self,
        step_outputs: dict[str, dict[str, Any]],
        step_phases: dict[str, str],
    ) -> None:
        """Checks in a different phase are not emitted."""
        validations: dict[str, Any] = {
            "setup_checks": {
                "step": "launch_instance",
                "checks": {"InstanceStateCheck": {"expected_state": "running"}},
            },
            "instance_info": {
                "step": "describe_instance",
                "checks": {"InstanceStateCheck": {"expected_state": "running"}},
            },
        }
        result = _transform_validations_for_pytest(validations, step_outputs, step_phases, "test")
        keys = self._keys(result)
        # Only the test-phase entry should appear, and since it's the only one
        # for this phase, it keeps the bare class name.
        assert keys == ["InstanceStateCheck"]

    def test_empty_validations(self) -> None:
        """Empty input returns empty list."""
        assert _transform_validations_for_pytest({}, {}, {}, "test") == []

    def test_unreleased_checks_are_skipped(
        self,
        step_outputs: dict[str, dict[str, Any]],
        step_phases: dict[str, str],
    ) -> None:
        """Configured checks not in the release manifest are not emitted."""
        validations: dict[str, Any] = {
            "ssh": {
                "step": "describe_instance",
                "checks": {"ConnectivityCheck": {}, "NewMainOnlyCheck": {}},
            },
        }
        result = _transform_validations_for_pytest(
            validations,
            step_outputs,
            step_phases,
            "test",
            released_tests={"ConnectivityCheck"},
        )
        assert self._keys(result) == ["ConnectivityCheck"]

    def test_disabled_release_filter_includes_all_checks(
        self,
        step_outputs: dict[str, dict[str, Any]],
        step_phases: dict[str, str],
    ) -> None:
        """A disabled release filter emits configured checks regardless of manifest membership."""
        validations: dict[str, Any] = {
            "ssh": {
                "step": "describe_instance",
                "checks": {"ConnectivityCheck": {}, "NewMainOnlyCheck": {}},
            },
        }
        result = _transform_validations_for_pytest(
            validations,
            step_outputs,
            step_phases,
            "test",
            released_tests=None,
        )
        assert self._keys(result) == ["ConnectivityCheck", "NewMainOnlyCheck"]

    def test_list_format_dedup(self) -> None:
        """Duplicate class names in legacy list format also get qualified."""
        step_outputs = {
            "step_a": {"ok": True},
            "step_b": {"ok": True},
        }
        step_phases = {"step_a": "test", "step_b": "test"}
        validations: dict[str, Any] = {
            "cat_a": [
                {"StepSuccessCheck": {"step": "step_a"}},
            ],
            "cat_b": [
                {"StepSuccessCheck": {"step": "step_b"}},
            ],
        }
        result = _transform_validations_for_pytest(validations, step_outputs, step_phases, "test")
        keys = self._keys(result)
        assert "StepSuccessCheck-cat_a" in keys
        assert "StepSuccessCheck-cat_b" in keys

    def test_same_class_same_category_gets_counter(self) -> None:
        """Same class repeated in one category gets a numeric disambiguator."""
        step_outputs = {
            "step_a": {"ok": True},
            "step_b": {"ok": True},
        }
        step_phases = {"step_a": "test", "step_b": "test"}
        validations: dict[str, Any] = {
            "checks": [
                {"StepSuccessCheck": {"step": "step_a"}},
                {"StepSuccessCheck": {"step": "step_b"}},
            ],
        }
        result = _transform_validations_for_pytest(validations, step_outputs, step_phases, "test")
        keys = self._keys(result)
        assert "StepSuccessCheck-checks" in keys
        assert "StepSuccessCheck-checks-2" in keys
        assert len(keys) == 2
