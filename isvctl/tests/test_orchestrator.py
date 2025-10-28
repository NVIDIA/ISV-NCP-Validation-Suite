"""Tests for orchestration components."""

import tempfile
from pathlib import Path

from isvctl.config.schema import CommandConfig, CommandOutput, RunConfig
from isvctl.orchestrator.commands import CommandExecutor
from isvctl.orchestrator.context import Context


class TestCommandExecutor:
    """Tests for CommandExecutor."""

    def test_execute_simple_command(self) -> None:
        """Test executing a simple echo command."""
        executor = CommandExecutor()
        config = CommandConfig(command="echo", args=["hello"])

        result = executor.execute(config)

        assert result.success
        assert result.exit_code == 0
        assert "hello" in result.stdout

    def test_execute_skipped_command(self) -> None:
        """Test that skipped commands succeed immediately."""
        executor = CommandExecutor()
        config = CommandConfig(skip=True)

        result = executor.execute(config)

        assert result.success
        assert result.error == "Command skipped"

    def test_execute_missing_command(self) -> None:
        """Test handling of missing command."""
        executor = CommandExecutor()
        config = CommandConfig()  # No command specified

        result = executor.execute(config)

        assert not result.success
        assert "No command specified" in result.error

    def test_execute_with_context(self) -> None:
        """Test templating context in arguments."""
        executor = CommandExecutor()
        config = CommandConfig(command="echo", args=["nodes={{context.node_count}}"])
        context = {"context": {"node_count": 8}}

        result = executor.execute(config, context=context)

        assert result.success
        assert "nodes=8" in result.stdout

    def test_validate_json_output(self) -> None:
        """Test JSON output validation."""
        executor = CommandExecutor()

        # Create a script that outputs valid JSON
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
            f.write(
                """#!/bin/bash
cat << 'EOF'
{"platform": "kubernetes", "cluster_name": "test-123", "kubernetes": {"node_count": 4}}
EOF
"""
            )
            script_path = f.name

        try:
            Path(script_path).chmod(0o755)

            config = CommandConfig(command=script_path)
            result = executor.execute(config, validate_output=True)

            assert result.success
            assert result.output is not None
            assert result.output.platform == "kubernetes"
            assert result.output.cluster_name == "test-123"
        finally:
            Path(script_path).unlink(missing_ok=True)

    def test_validate_invalid_json(self) -> None:
        """Test handling of invalid JSON output."""
        executor = CommandExecutor()
        config = CommandConfig(command="echo", args=["not json"])

        result = executor.execute(config, validate_output=True)

        assert not result.success
        assert "Invalid JSON" in result.error

    def test_execute_with_env_vars(self) -> None:
        """Test execution with custom environment variables."""
        executor = CommandExecutor()
        config = CommandConfig(command="sh", args=["-c", "echo $MY_VAR"], env={"MY_VAR": "test-value"})

        result = executor.execute(config)

        assert result.success
        assert "test-value" in result.stdout

    def test_execute_command_timeout(self) -> None:
        """Test handling of command timeout."""
        executor = CommandExecutor()
        config = CommandConfig(command="sleep", args=["10"], timeout=1)

        result = executor.execute(config)

        assert not result.success
        assert "timed out" in result.error

    def test_execute_command_not_found(self) -> None:
        """Test handling of non-existent command."""
        executor = CommandExecutor()
        config = CommandConfig(command="nonexistent_command_xyz")

        result = executor.execute(config)

        assert not result.success
        assert "Command not found" in result.error

    def test_execute_with_nonzero_exit_code(self) -> None:
        """Test handling of command with nonzero exit code."""
        executor = CommandExecutor()
        config = CommandConfig(command="sh", args=["-c", "echo error >&2; exit 42"])

        result = executor.execute(config)

        assert not result.success
        assert result.exit_code == 42
        assert "error" in result.error  # stderr included in error message

    def test_template_rendering_error(self) -> None:
        """Test handling of template rendering errors in args."""
        executor = CommandExecutor()
        config = CommandConfig(command="echo", args=["{{undefined.variable}}"])

        # Should not crash, should fall back to original arg
        result = executor.execute(config, context={})

        # The arg rendering fails but command still executes
        assert result.success

    def test_validate_empty_output(self) -> None:
        """Test validation of empty command output."""
        executor = CommandExecutor()
        config = CommandConfig(command="echo", args=[""])

        result = executor.execute(config, validate_output=True)

        assert not result.success
        assert "no output" in result.error

    def test_validate_output_validation_error(self) -> None:
        """Test handling of pydantic validation errors."""
        executor = CommandExecutor()

        # Create a script that outputs JSON but doesn't match schema
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
            f.write(
                """#!/bin/bash
cat << 'EOF'
{"invalid": "schema"}
EOF
"""
            )
            script_path = f.name

        try:
            Path(script_path).chmod(0o755)

            config = CommandConfig(command=script_path)
            result = executor.execute(config, validate_output=True)

            assert not result.success
            assert "validation failed" in result.error
        finally:
            Path(script_path).unlink(missing_ok=True)


class TestContext:
    """Tests for Context class."""

    def test_initial_context(self) -> None:
        """Test context initialization."""
        config = RunConfig(
            context={"node_count": 4},
            lab={"id": "lab-001", "name": "Test Lab"},
        )
        context = Context(config)

        assert context.data["context"]["node_count"] == 4
        assert context.data["lab"]["id"] == "lab-001"
        assert "timestamp" in context.data["builtin"]

    def test_set_inventory(self) -> None:
        """Test setting inventory from command output."""
        config = RunConfig()
        context = Context(config)

        output = CommandOutput(
            platform="kubernetes",
            cluster_name="test-cluster",
            kubernetes={"node_count": 4, "total_gpus": 16},
        )
        context.set_inventory(output)

        assert context.data["inventory"]["platform"] == "kubernetes"
        assert context.data["inventory"]["cluster_name"] == "test-cluster"
        assert context.data["inventory"]["kubernetes"]["node_count"] == 4

    def test_render_string(self) -> None:
        """Test Jinja2 template rendering."""
        config = RunConfig(context={"node_count": 8})
        context = Context(config)

        result = context.render_string("nodes: {{context.node_count}}")
        assert result == "nodes: 8"

    def test_render_dict(self) -> None:
        """Test recursive dict rendering."""
        config = RunConfig(context={"name": "test"})
        context = Context(config)

        data = {
            "cluster": "{{context.name}}",
            "nested": {"value": "prefix-{{context.name}}"},
            "list": ["{{context.name}}", "static"],
        }
        result = context.render_dict(data)

        assert result["cluster"] == "test"
        assert result["nested"]["value"] == "prefix-test"
        assert result["list"] == ["test", "static"]

    def test_to_inventory_dict(self) -> None:
        """Test conversion to isvtest inventory format."""
        config = RunConfig()
        context = Context(config)

        output = CommandOutput(
            platform="kubernetes",
            cluster_name="my-cluster",
            kubernetes={
                "node_count": 4,
                "driver_version": "580.95.05",
            },
        )
        context.set_inventory(output)

        inventory = context.to_inventory_dict()
        assert inventory["platform"] == "kubernetes"
        assert inventory["cluster_name"] == "my-cluster"

    def test_get_command_context(self) -> None:
        """Test getting context for command templating."""
        config = RunConfig(context={"node_count": 8}, lab={"id": "lab-001"})
        context = Context(config)

        cmd_context = context.get_command_context()
        assert cmd_context["context"]["node_count"] == 8
        assert cmd_context["lab"]["id"] == "lab-001"

    def test_get_test_context(self) -> None:
        """Test getting context for test configuration."""
        config = RunConfig(context={"gpu_count": 4})
        context = Context(config)

        test_context = context.get_test_context()
        assert test_context["context"]["gpu_count"] == 4

    def test_render_string_without_templates(self) -> None:
        """Test that strings without templates pass through unchanged."""
        config = RunConfig()
        context = Context(config)

        result = context.render_string("plain string without templates")
        assert result == "plain string without templates"

    def test_render_dict_with_non_string_values(self) -> None:
        """Test rendering dict with non-string/dict/list values."""
        config = RunConfig(context={"name": "test"})
        context = Context(config)

        data = {
            "template": "{{context.name}}",
            "integer": 42,
            "boolean": True,
            "none_value": None,
            "float": 3.14,
        }
        result = context.render_dict(data)

        assert result["template"] == "test"
        assert result["integer"] == 42
        assert result["boolean"] is True
        assert result["none_value"] is None
        assert result["float"] == 3.14

    def test_render_list_with_nested_structures(self) -> None:
        """Test rendering list with nested dicts and lists."""
        config = RunConfig(context={"name": "test"})
        context = Context(config)

        data = {
            "items": [
                "{{context.name}}",
                {"key": "{{context.name}}"},
                ["nested-{{context.name}}", 42],
                123,
                True,
                None,
            ]
        }
        result = context.render_dict(data)

        assert result["items"][0] == "test"
        assert result["items"][1]["key"] == "test"
        assert result["items"][2][0] == "nested-test"
        assert result["items"][2][1] == 42
        assert result["items"][3] == 123
        assert result["items"][4] is True
        assert result["items"][5] is None
