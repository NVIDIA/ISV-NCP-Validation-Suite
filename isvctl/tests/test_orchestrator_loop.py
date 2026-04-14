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
from unittest.mock import patch

from isvctl.config.schema import PlatformCommands, RunConfig, StepConfig, ValidationConfig
from isvctl.orchestrator.context import Context
from isvctl.orchestrator.loop import Orchestrator, Phase
from isvctl.orchestrator.step_executor import StepExecutor


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
        """Test teardown phase execution when only teardown is requested.

        Covers the use case where setup ran in a previous invocation (e.g., with
        AWS_SKIP_TEARDOWN) and now the user explicitly runs ``--phase teardown``
        to clean up resources.
        """
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
        assert "SKIPPED" not in result.phases[0].message, "teardown must actually run, not be skipped"
        step_names = [s["name"] for s in result.phases[0].details["steps"]]
        assert "cleanup" in step_names, "teardown step must have executed"

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

    def test_teardown_runs_when_setup_validation_fails(self) -> None:
        """Teardown must run when setup steps succeed but setup validations fail.

        Regression test for issue where validation failures in setup caused
        teardown to be skipped, leaking cloud resources.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
            f.write(
                '#!/bin/bash\necho \'{"success": true, "platform": "kubernetes", '
                '"cluster_name": "test", "node_count": 1, "kubernetes": {"node_count": 1}}\'\n'
            )
            setup_script = f.name

        try:
            Path(setup_script).chmod(0o755)

            config = RunConfig(
                commands={
                    "kubernetes": PlatformCommands(
                        steps=[
                            StepConfig(name="setup_cluster", command=setup_script, phase="setup"),
                            StepConfig(name="cleanup", command="echo", args=["done"], phase="teardown"),
                        ]
                    )
                },
                tests=ValidationConfig(platform="kubernetes"),
            )
            orchestrator = Orchestrator(config)

            failing_validations = [{"name": "FakeCheck", "passed": False, "error": "simulated"}]
            with patch.object(
                orchestrator.step_executor,
                "run_validations_for_phase",
                side_effect=lambda phase, *a, **kw: failing_validations if phase == "setup" else [],
            ):
                result = orchestrator.run(teardown_on_failure=True)

            assert not result.success
            teardown_phases = [p for p in result.phases if p.phase == Phase.TEARDOWN]
            assert len(teardown_phases) == 1, "teardown phase must run even when setup validations fail"
            teardown_step_names = [s["name"] for s in teardown_phases[0].details["steps"]]
            assert "cleanup" in teardown_step_names, "teardown step must have executed"
        finally:
            Path(setup_script).unlink(missing_ok=True)

    def test_teardown_skipped_when_setup_steps_did_not_run(self) -> None:
        """Teardown must be skipped when no setup steps executed."""
        config = RunConfig(
            commands={
                "kubernetes": PlatformCommands(
                    phases=["setup", "teardown"],
                    steps=[
                        StepConfig(name="setup_cluster", command="echo", args=["hi"], phase="setup", skip=True),
                        StepConfig(name="cleanup", command="echo", args=["bye"], phase="teardown"),
                    ],
                )
            },
            tests=ValidationConfig(platform="kubernetes"),
        )
        orchestrator = Orchestrator(config)
        result = orchestrator.run(teardown_on_failure=True)

        teardown_phases = [p for p in result.phases if p.phase == Phase.TEARDOWN]
        assert len(teardown_phases) == 1
        assert "SKIPPED" in teardown_phases[0].message
        assert "setup steps did not run" in teardown_phases[0].message

    def test_teardown_continues_after_step_failure(self) -> None:
        """All teardown steps must run even if an earlier teardown step fails.

        Regression test for issue where the first failing teardown step caused
        remaining teardown steps to be skipped (e.g., VM not deleted after
        NIM teardown failed).
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
            f.write(
                '#!/bin/bash\necho \'{"success": true, "platform": "kubernetes", '
                '"cluster_name": "test", "node_count": 1, "kubernetes": {"node_count": 1}}\'\n'
            )
            setup_script = f.name

        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
            f.write("#!/bin/bash\necho '{\"success\": true}'\n")
            teardown_ok_script = f.name

        try:
            Path(setup_script).chmod(0o755)
            Path(teardown_ok_script).chmod(0o755)

            config = RunConfig(
                commands={
                    "kubernetes": PlatformCommands(
                        steps=[
                            StepConfig(name="setup_cluster", command=setup_script, phase="setup"),
                            StepConfig(name="teardown_nim", command="false", phase="teardown"),
                            StepConfig(name="teardown_vm", command=teardown_ok_script, phase="teardown"),
                        ]
                    )
                },
                tests=ValidationConfig(platform="kubernetes"),
            )
            orchestrator = Orchestrator(config)
            result = orchestrator.run(teardown_on_failure=True)

            teardown_phases = [p for p in result.phases if p.phase == Phase.TEARDOWN]
            assert len(teardown_phases) == 1

            step_names = [s["name"] for s in teardown_phases[0].details["steps"]]
            assert "teardown_nim" in step_names, "first teardown step must be recorded"
            assert "teardown_vm" in step_names, "second teardown step must run despite first failure"
        finally:
            Path(setup_script).unlink(missing_ok=True)
            Path(teardown_ok_script).unlink(missing_ok=True)


class TestTeardownOnlyPhase:
    """Tests for running teardown as the only requested phase.

    Covers the workflow where setup ran in a prior invocation (e.g., with
    AWS_SKIP_TEARDOWN set) and the user later runs ``--phase teardown`` to
    clean up resources from that earlier run.
    """

    def test_teardown_only_runs_without_setup(self) -> None:
        """Teardown must execute when it is the only requested phase.

        When a user explicitly requests ``--phase teardown``, it should run
        regardless of whether setup ran in this invocation.
        """
        config = RunConfig(
            commands={
                "kubernetes": PlatformCommands(
                    steps=[
                        StepConfig(name="setup_cluster", command="echo", args=["hi"], phase="setup"),
                        StepConfig(name="cleanup", command="echo", args=["bye"], phase="teardown"),
                    ]
                )
            },
            tests=ValidationConfig(platform="kubernetes"),
        )
        orchestrator = Orchestrator(config)
        result = orchestrator.run(phases=[Phase.TEARDOWN])

        assert result.success
        teardown_phases = [p for p in result.phases if p.phase == Phase.TEARDOWN]
        assert len(teardown_phases) == 1
        assert teardown_phases[0].success
        assert "SKIPPED" not in teardown_phases[0].message
        step_names = [s["name"] for s in teardown_phases[0].details["steps"]]
        assert "cleanup" in step_names

    def test_teardown_only_does_not_run_setup_steps(self) -> None:
        """When only teardown is requested, setup steps must not execute."""
        config = RunConfig(
            commands={
                "kubernetes": PlatformCommands(
                    steps=[
                        StepConfig(name="setup_cluster", command="echo", args=["created"], phase="setup"),
                        StepConfig(name="cleanup", command="echo", args=["deleted"], phase="teardown"),
                    ]
                )
            },
            tests=ValidationConfig(platform="kubernetes"),
        )
        orchestrator = Orchestrator(config)
        result = orchestrator.run(phases=[Phase.TEARDOWN])

        setup_phases = [p for p in result.phases if p.phase == Phase.SETUP]
        assert len(setup_phases) == 0, "setup phase must not appear when only teardown is requested"

    def test_teardown_only_best_effort_continues_past_failures(self) -> None:
        """Teardown-only run must use best-effort so all cleanup steps execute."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
            f.write("#!/bin/bash\necho '{\"success\": true}'\n")
            ok_script = f.name

        try:
            Path(ok_script).chmod(0o755)

            config = RunConfig(
                commands={
                    "kubernetes": PlatformCommands(
                        steps=[
                            StepConfig(name="teardown_nim", command="false", phase="teardown"),
                            StepConfig(name="teardown_vm", command=ok_script, phase="teardown"),
                        ]
                    )
                },
                tests=ValidationConfig(platform="kubernetes"),
            )
            orchestrator = Orchestrator(config)
            result = orchestrator.run(phases=[Phase.TEARDOWN])

            teardown_phases = [p for p in result.phases if p.phase == Phase.TEARDOWN]
            assert len(teardown_phases) == 1
            step_names = [s["name"] for s in teardown_phases[0].details["steps"]]
            assert "teardown_nim" in step_names, "failing teardown step must be recorded"
            assert "teardown_vm" in step_names, "second teardown step must run despite first failure"
        finally:
            Path(ok_script).unlink(missing_ok=True)

    def test_teardown_still_skipped_when_setup_requested_but_did_not_run(self) -> None:
        """When both setup and teardown are requested, teardown is still gated on setup execution.

        This ensures the existing safety guard stays in place for full lifecycle runs.
        """
        config = RunConfig(
            commands={
                "kubernetes": PlatformCommands(
                    phases=["setup", "teardown"],
                    steps=[
                        StepConfig(name="setup_cluster", command="echo", args=["hi"], phase="setup", skip=True),
                        StepConfig(name="cleanup", command="echo", args=["bye"], phase="teardown"),
                    ],
                )
            },
            tests=ValidationConfig(platform="kubernetes"),
        )
        orchestrator = Orchestrator(config)
        result = orchestrator.run(phases=[Phase.SETUP, Phase.TEARDOWN], teardown_on_failure=True)

        teardown_phases = [p for p in result.phases if p.phase == Phase.TEARDOWN]
        assert len(teardown_phases) == 1
        assert "SKIPPED" in teardown_phases[0].message
        assert "setup steps did not run" in teardown_phases[0].message


class TestStepExecutorBestEffort:
    """Tests for StepExecutor best_effort parameter."""

    def test_best_effort_false_stops_on_failure(self) -> None:
        """Without best_effort, execution stops after the first failing step."""
        executor = StepExecutor()
        context = Context(RunConfig())
        steps = [
            StepConfig(name="fail_step", command="false", phase="teardown"),
            StepConfig(name="ok_step", command="echo", args=["hi"], phase="teardown"),
        ]

        results = executor.execute_steps(steps, context, best_effort=False)

        assert not results.success
        executed = [s.name for s in results.steps]
        assert executed == ["fail_step"], "second step must NOT run when best_effort is False"

    def test_best_effort_true_continues_on_failure(self) -> None:
        """With best_effort, all steps execute even when one fails."""
        executor = StepExecutor()
        context = Context(RunConfig())
        steps = [
            StepConfig(name="fail_step", command="false", phase="teardown"),
            StepConfig(name="ok_step", command="echo", args=["hi"], phase="teardown"),
        ]

        results = executor.execute_steps(steps, context, best_effort=True)

        assert not results.success
        executed = [s.name for s in results.steps]
        assert executed == ["fail_step", "ok_step"], "second step must run when best_effort is True"
        assert not results.steps[0].success
        assert results.steps[1].success

    def test_best_effort_respects_continue_on_failure(self) -> None:
        """Steps with continue_on_failure=True continue regardless of best_effort."""
        executor = StepExecutor()
        context = Context(RunConfig())
        steps = [
            StepConfig(name="fail_step", command="false", phase="setup", continue_on_failure=True),
            StepConfig(name="ok_step", command="echo", args=["hi"], phase="setup"),
        ]

        results = executor.execute_steps(steps, context, best_effort=False)

        executed = [s.name for s in results.steps]
        assert executed == ["fail_step", "ok_step"]
