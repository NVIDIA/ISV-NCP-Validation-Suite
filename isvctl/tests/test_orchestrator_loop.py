# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Tests for orchestrator loop."""

import tempfile
from pathlib import Path

from isvctl.config.schema import PlatformCommands, RunConfig, StepConfig, ValidationConfig
from isvctl.orchestrator.loop import Orchestrator, Phase


class TestOrchestrator:
    """Tests for Orchestrator class."""

    def test_detect_platform_from_config(self) -> None:
        """Test platform detection from test config."""
        config = RunConfig(
            commands={
                "kubernetes": PlatformCommands(
                    steps=[StepConfig(name="setup", command="echo", args=["test"], phase="setup")]
                )
            },
            tests=ValidationConfig(platform="kubernetes"),
        )
        orchestrator = Orchestrator(config)

        platform = orchestrator._detect_platform()
        assert platform == "kubernetes"

    def test_run_setup_phase_success(self) -> None:
        """Test successful setup phase execution."""
        # Create a script that outputs valid JSON inventory
        # Must match the "cluster" schema: success, platform, cluster_name, node_count (at root)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
            f.write(
                """#!/bin/bash
cat << 'EOF'
{"success": true, "platform": "kubernetes", "cluster_name": "test-cluster", "node_count": 4, "kubernetes": {"node_count": 4}}
EOF
"""
            )
            script_path = f.name

        try:
            Path(script_path).chmod(0o755)

            config = RunConfig(
                commands={
                    "kubernetes": PlatformCommands(
                        steps=[
                            StepConfig(name="setup_cluster", command=script_path, phase="setup"),
                        ]
                    )
                },
                tests=ValidationConfig(platform="kubernetes"),
            )
            orchestrator = Orchestrator(config)

            result = orchestrator.run(phases=[Phase.SETUP])

            assert result.success
            assert len(result.phases) == 1
            assert result.phases[0].phase == Phase.SETUP
            assert result.phases[0].success
            assert result.inventory is not None
            assert "setup_cluster" in result.inventory
        finally:
            Path(script_path).unlink(missing_ok=True)

    def test_run_setup_phase_command_failure(self) -> None:
        """Test setup phase with command failure."""
        config = RunConfig(
            commands={
                "kubernetes": PlatformCommands(
                    steps=[
                        StepConfig(name="failing_setup", command="false", phase="setup"),
                    ]
                )
            },
            tests=ValidationConfig(platform="kubernetes"),
        )
        orchestrator = Orchestrator(config)

        result = orchestrator.run(phases=[Phase.SETUP])

        assert not result.success
        assert len(result.phases) == 1
        assert not result.phases[0].success
        assert "failed" in result.phases[0].message.lower()

    def test_run_skip_setup_phase(self) -> None:
        """Test skipping setup phase (platform-level skip)."""
        config = RunConfig(
            commands={"kubernetes": PlatformCommands(skip=True)},
            tests=ValidationConfig(platform="kubernetes"),
        )
        orchestrator = Orchestrator(config)

        result = orchestrator.run(phases=[Phase.SETUP])

        # When platform is skipped, no steps are returned which results in "No steps defined"
        assert not result.success
        assert "No steps defined" in result.phases[0].message

    def test_run_test_phase_requires_steps(self) -> None:
        """Test that test phase with no steps fails gracefully."""
        config = RunConfig(
            commands={
                "kubernetes": PlatformCommands(
                    steps=[]  # No steps defined
                )
            },
            tests=ValidationConfig(platform="kubernetes", cluster_name="test"),
        )
        orchestrator = Orchestrator(config)

        result = orchestrator.run(phases=[Phase.TEST])

        assert not result.success
        assert "No steps defined" in result.phases[0].message

    def test_run_test_phase_with_mocked_pytest_skip(self) -> None:
        """Skip complex test phase mocking - covered by integration tests."""
        pass

    def test_run_teardown_phase(self) -> None:
        """Test teardown phase execution."""
        config = RunConfig(
            commands={
                "kubernetes": PlatformCommands(
                    steps=[
                        StepConfig(name="cleanup", command="echo", args=["cleanup"], phase="teardown"),
                    ]
                )
            },
            tests=ValidationConfig(platform="kubernetes"),
        )
        orchestrator = Orchestrator(config)

        result = orchestrator.run(phases=[Phase.TEARDOWN])

        assert result.success
        assert len(result.phases) == 1
        assert result.phases[0].phase == Phase.TEARDOWN
        assert result.phases[0].success

    def test_run_all_phases_with_failure(self) -> None:
        """Test that teardown runs even after setup failure."""
        config = RunConfig(
            commands={
                "kubernetes": PlatformCommands(
                    steps=[
                        StepConfig(name="failing_setup", command="false", phase="setup"),
                        StepConfig(name="cleanup", command="echo", args=["cleanup"], phase="teardown"),
                    ]
                )
            },
            tests=ValidationConfig(platform="kubernetes"),
        )
        orchestrator = Orchestrator(config)

        result = orchestrator.run(teardown_on_failure=True)

        # Overall should fail due to setup
        assert not result.success
        # But teardown should still have run
        teardown_phases = [p for p in result.phases if p.phase == Phase.TEARDOWN]
        assert len(teardown_phases) == 1
        assert teardown_phases[0].success

    def test_platform_detection_missing(self) -> None:
        """Test error when platform cannot be detected."""
        config = RunConfig(
            commands={},
            tests=ValidationConfig(),  # No platform specified
        )
        orchestrator = Orchestrator(config)

        result = orchestrator.run()

        assert not result.success
        assert "Cannot determine platform" in result.phases[0].message
