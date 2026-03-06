# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Tests for Pydantic schema models."""

import pytest
from pydantic import ValidationError

from isvctl.config.schema import CommandConfig, CommandOutput, PlatformCommands, RunConfig, StepConfig


class TestCommandConfig:
    """Tests for CommandConfig model."""

    def test_minimal_config(self) -> None:
        """Test creating a minimal command config."""
        config = CommandConfig()
        assert config.command is None
        assert config.args == []
        assert config.timeout == 300
        assert config.skip is False

    def test_full_config(self) -> None:
        """Test creating a fully specified command config."""
        config = CommandConfig(
            command="./stubs/k8s-create.sh",
            args=["--nodes", "4"],
            timeout=600,
            skip=False,
            working_dir="/tmp",
            env={"FOO": "bar"},
        )
        assert config.command == "./stubs/k8s-create.sh"
        assert config.args == ["--nodes", "4"]
        assert config.timeout == 600
        assert config.env == {"FOO": "bar"}

    def test_skip_flag(self) -> None:
        """Test skip flag for unsupported commands."""
        config = CommandConfig(skip=True)
        assert config.skip is True
        assert config.command is None


class TestStepConfig:
    """Tests for StepConfig model."""

    def test_minimal_step(self) -> None:
        """Test creating a minimal step config."""
        step = StepConfig(name="test_step", command="echo")
        assert step.name == "test_step"
        assert step.command == "echo"
        assert step.args == []
        assert step.timeout == 300
        assert step.phase == "setup"
        assert step.skip is False

    def test_full_step(self) -> None:
        """Test creating a fully specified step config."""
        step = StepConfig(
            name="create_vpc",
            command="./scripts/create_vpc.py",
            args=["--name", "test-vpc"],
            timeout=600,
            env={"AWS_REGION": "us-west-2"},
            working_dir="/tmp",
            phase="setup",
            skip=False,
            continue_on_failure=True,
            output_schema="vpc",
        )
        assert step.name == "create_vpc"
        assert step.command == "./scripts/create_vpc.py"
        assert step.args == ["--name", "test-vpc"]
        assert step.timeout == 600
        assert step.env == {"AWS_REGION": "us-west-2"}
        assert step.phase == "setup"
        assert step.continue_on_failure is True
        assert step.output_schema == "vpc"


class TestCommandOutput:
    """Tests for CommandOutput model (setup command JSON output)."""

    def test_kubernetes_output(self) -> None:
        """Test parsing Kubernetes setup output."""
        output = CommandOutput(
            platform="kubernetes",
            cluster_name="test-cluster",
            kubernetes={
                "node_count": 4,
                "nodes": ["node1", "node2", "node3", "node4"],
                "total_gpus": 16,
                "driver_version": "580.95.05",
            },
        )
        assert output.platform == "kubernetes"
        assert output.cluster_name == "test-cluster"
        assert output.kubernetes is not None
        assert output.kubernetes.node_count == 4
        assert output.kubernetes.total_gpus == 16

    def test_slurm_output(self) -> None:
        """Test parsing Slurm setup output."""
        output = CommandOutput(
            platform="slurm",
            cluster_name="slurm-cluster",
            slurm={
                "partitions": {
                    "gpu": {"nodes": ["gpu1", "gpu2"], "node_count": 2},
                    "cpu": {"nodes": ["cpu1"], "node_count": 1},
                },
                "cuda_arch": "90",
            },
        )
        assert output.platform == "slurm"
        assert output.slurm is not None
        assert "gpu" in output.slurm.partitions
        assert output.slurm.cuda_arch == "90"

    def test_missing_required_fields(self) -> None:
        """Test that missing required fields raise ValidationError."""
        with pytest.raises(ValidationError):
            CommandOutput()  # Missing platform and cluster_name


class TestRunConfigModel:
    """Tests for RunConfig model."""

    def test_empty_config(self) -> None:
        """Test creating an empty config."""
        config = RunConfig()
        assert config.version == "1.0"
        assert config.commands == {}
        assert config.context == {}

    def test_get_steps(self) -> None:
        """Test getting steps for a platform."""
        config = RunConfig(
            commands={
                "kubernetes": PlatformCommands(
                    steps=[
                        StepConfig(name="setup_cluster", command="./k8s-setup.sh", phase="setup"),
                        StepConfig(name="teardown_cluster", command="./k8s-teardown.sh", phase="teardown"),
                    ]
                ),
                "slurm": PlatformCommands(
                    steps=[
                        StepConfig(name="skipped_step", command="./slurm-setup.sh", skip=True),
                    ]
                ),
            }
        )

        k8s_steps = config.get_steps("kubernetes")
        assert len(k8s_steps) == 2
        assert k8s_steps[0].command == "./k8s-setup.sh"

        # Skipped steps are filtered out
        slurm_steps = config.get_steps("slurm")
        assert len(slurm_steps) == 0

    def test_platform_level_skip(self) -> None:
        """Test platform-level skip skips all phases."""
        config = RunConfig(
            commands={
                "kubernetes": PlatformCommands(
                    steps=[
                        StepConfig(name="setup_cluster", command="./k8s-setup.sh", phase="setup"),
                        StepConfig(name="teardown_cluster", command="./k8s-teardown.sh", phase="teardown"),
                    ]
                ),
                # Platform-level skip - simpler than skipping each step
                "slurm": PlatformCommands(skip=True),
            }
        )

        # Kubernetes should have steps
        k8s_steps = config.get_steps("kubernetes")
        assert len(k8s_steps) == 2

        # Slurm should be skipped at platform level (returns empty list)
        slurm_steps = config.get_steps("slurm")
        assert len(slurm_steps) == 0

    def test_get_phases(self) -> None:
        """Test getting phases for a platform."""
        config = RunConfig(
            commands={
                "kubernetes": PlatformCommands(
                    phases=["setup", "test", "teardown"],
                    steps=[
                        StepConfig(name="setup_cluster", command="./k8s-setup.sh", phase="setup"),
                    ],
                ),
            }
        )

        phases = config.get_phases("kubernetes")
        assert phases == ["setup", "test", "teardown"]

    def test_full_config(self) -> None:
        """Test parsing a full configuration with steps."""
        config = RunConfig.model_validate(
            {
                "version": "1.0",
                "lab": {"id": "lab-001", "name": "Test Lab"},
                "commands": {
                    "kubernetes": {
                        "phases": ["setup", "teardown"],
                        "steps": [
                            {
                                "name": "setup_cluster",
                                "command": "./k8s-setup.sh",
                                "args": ["--nodes", "4"],
                                "timeout": 600,
                                "phase": "setup",
                            },
                            {
                                "name": "teardown_cluster",
                                "command": "./k8s-teardown.sh",
                                "phase": "teardown",
                            },
                        ],
                    }
                },
                "context": {"node_count": 4},
                "tests": {
                    "platform": "kubernetes",
                    "validations": {"kubernetes": [{"K8sNodeCountCheck": {"count": 4}}]},
                },
            }
        )
        assert config.lab is not None
        assert config.lab.id == "lab-001"
        assert config.tests is not None
        assert config.tests.platform == "kubernetes"
        # Verify step-based command structure
        steps = config.get_steps("kubernetes")
        assert len(steps) == 2
        assert steps[0].name == "setup_cluster"
        assert steps[0].command == "./k8s-setup.sh"
        assert steps[1].name == "teardown_cluster"
        assert steps[1].command == "./k8s-teardown.sh"
