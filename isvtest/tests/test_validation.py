"""Tests for validation module."""

from unittest.mock import MagicMock

from isvtest.core.runners import CommandResult
from isvtest.core.validation import BaseValidation


class ConcreteValidation(BaseValidation):
    """Concrete implementation for testing."""

    description = "Test validation"
    timeout = 30

    def run(self) -> None:
        """Simple run implementation."""
        self.set_passed("Test passed")


class FailingValidation(BaseValidation):
    """Validation that always fails."""

    def run(self) -> None:
        """Fail the validation."""
        self.set_failed("Test failed", "Error output")


class ExceptionValidation(BaseValidation):
    """Validation that raises an exception."""

    def run(self) -> None:
        """Raise an exception."""
        raise RuntimeError("Unexpected error")


class TestBaseValidation:
    """Tests for BaseValidation class."""

    def test_init_with_defaults(self) -> None:
        """Test initialization with default values."""
        validation = ConcreteValidation()
        assert validation.name == "ConcreteValidation"
        assert validation.config == {}
        assert validation._passed is False
        assert validation._output == ""
        assert validation._error == ""

    def test_init_with_config(self) -> None:
        """Test initialization with custom config."""
        config = {"key": "value", "nested": {"inner": 42}}
        validation = ConcreteValidation(config=config)
        assert validation.config == config

    def test_set_passed(self) -> None:
        """Test set_passed method."""
        validation = ConcreteValidation()
        validation.set_passed("Success message")

        assert validation._passed is True
        assert validation._output == "Success message"

    def test_set_passed_without_message(self) -> None:
        """Test set_passed without message."""
        validation = ConcreteValidation()
        validation.set_passed()

        assert validation._passed is True
        assert validation._output == ""

    def test_set_failed(self) -> None:
        """Test set_failed method."""
        validation = ConcreteValidation()
        validation.set_failed("Error message", "Error output")

        assert validation._passed is False
        assert validation._error == "Error message"
        assert validation._output == "Error output"

    def test_set_failed_without_output(self) -> None:
        """Test set_failed without output."""
        validation = ConcreteValidation()
        validation.set_failed("Error message")

        assert validation._passed is False
        assert validation._error == "Error message"
        assert validation._output == ""

    def test_execute_returns_result_dict(self) -> None:
        """Test that execute returns a result dictionary."""
        validation = ConcreteValidation()
        result = validation.execute()

        assert isinstance(result, dict)
        assert result["name"] == "ConcreteValidation"
        assert result["passed"] is True
        assert result["output"] == "Test passed"
        assert result["error"] == ""
        assert result["description"] == "Test validation"
        assert "duration" in result
        assert result["duration"] >= 0

    def test_execute_with_failed_validation(self) -> None:
        """Test execute with a failing validation."""
        validation = FailingValidation()
        result = validation.execute()

        assert result["passed"] is False
        assert result["error"] == "Test failed"
        assert result["output"] == "Error output"

    def test_execute_catches_exceptions(self) -> None:
        """Test that execute catches exceptions from run()."""
        validation = ExceptionValidation()
        result = validation.execute()

        assert result["passed"] is False
        assert "Unexpected error" in result["error"]

    def test_run_command(self) -> None:
        """Test run_command method."""
        mock_runner = MagicMock()
        mock_runner.run.return_value = CommandResult(
            exit_code=0,
            stdout="command output",
            stderr="",
            duration=0.5,
        )

        validation = ConcreteValidation(runner=mock_runner)
        result = validation.run_command("echo hello")

        mock_runner.run.assert_called_once_with("echo hello", timeout=30)
        assert result.exit_code == 0
        assert result.stdout == "command output"

    def test_run_command_with_custom_timeout(self) -> None:
        """Test run_command with custom timeout."""
        mock_runner = MagicMock()
        mock_runner.run.return_value = CommandResult(
            exit_code=0,
            stdout="",
            stderr="",
            duration=0.1,
        )

        validation = ConcreteValidation(runner=mock_runner)
        validation.run_command("slow command", timeout=120)

        mock_runner.run.assert_called_once_with("slow command", timeout=120)

    def test_run_command_appends_to_results(self) -> None:
        """Test that run_command appends results to _results list."""
        mock_runner = MagicMock()
        mock_result = CommandResult(exit_code=0, stdout="", stderr="", duration=0.1)
        mock_runner.run.return_value = mock_result

        validation = ConcreteValidation(runner=mock_runner)
        validation.run_command("cmd1")
        validation.run_command("cmd2")

        assert len(validation._results) == 2

    def test_class_attributes(self) -> None:
        """Test that class attributes are accessible."""
        assert ConcreteValidation.description == "Test validation"
        assert ConcreteValidation.timeout == 30

    def test_logger_is_created(self) -> None:
        """Test that a logger is created for the validation."""
        validation = ConcreteValidation()
        assert validation.log is not None
        assert validation.log.name == "ConcreteValidation"
