from typing import ClassVar

from isvtest.core.validation import BaseValidation


class ExampleCheck(BaseValidation):
    """Example check demonstrating the BaseValidation pattern."""

    description = "An example check that verifies echo works."
    markers: ClassVar[list[str]] = []

    def run(self) -> None:
        result = self.run_command("echo 'hello world'")

        if result.exit_code != 0:
            self.set_failed(f"Command failed with exit code {result.exit_code}")
            return

        if "hello world" not in result.stdout:
            self.set_failed(f"Unexpected output: {result.stdout}")
            return

        self.set_passed("Echo command worked as expected")


class SecondExampleCheck(BaseValidation):
    """Second example check demonstrating the BaseValidation pattern."""

    description = "An example check that verifies echo works."
    markers: ClassVar[list[str]] = []

    def run(self) -> None:
        result = self.run_command("echo 'another example'")

        if result.exit_code != 0:
            self.set_failed(f"Command failed with exit code {result.exit_code}")
            return

        if "another example" not in result.stdout:
            self.set_failed(f"Unexpected output: {result.stdout}")
            return

        self.set_passed("Echo command worked as expected")
