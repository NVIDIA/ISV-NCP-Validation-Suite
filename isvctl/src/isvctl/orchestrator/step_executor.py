# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Step executor for sequential command execution.

This module implements the steps-based execution model where:
1. Commands execute sequentially
2. Each command produces JSON output validated against an auto-detected schema
3. Outputs accumulate in context for use in subsequent steps via Jinja2
4. Validations are defined separately in tests.validations and run after phases complete

Validations use Jinja2 templating to reference step outputs (e.g., {{steps.step_name.field}}).
Validation timing is determined by (in priority order):
1. Explicit `phase` field on the validation
2. Inferred from `step` - uses the step's phase
3. Default: 'test' phase

Example config:
    commands:
      kubernetes:
        steps:
          - name: setup
            phase: setup
            command: "./setup.sh"
          - name: teardown
            phase: teardown
            command: "./teardown.sh"

    tests:
      validations:
        cluster:
          - NodeCountCheck:
              step: setup
              expected: 4
"""

import json
import logging
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from isvctl.config.output_schemas import get_schema_for_step, validate_output
from isvctl.config.schema import StepConfig
from isvctl.orchestrator.context import Context, _create_jinja_env
from isvctl.redaction import mask_sensitive_args

logger = logging.getLogger(__name__)


_STEP_PATH_RE = re.compile(r"steps\.([\w.]+)")


class MissingStepRefError(Exception):
    """Raised when a step arg template references an undefined step output.

    This happens when a {{steps.X.Y}} path cannot be resolved in the context
    and the template has no `| default(...)` fallback — typically because an
    upstream step failed or was skipped. The caller should treat this as a
    signal to skip the step rather than passing a malformed empty argument
    to the underlying command.
    """

    def __init__(self, arg: str, path: str) -> None:
        self.arg = arg
        self.missing_path = path
        super().__init__(
            f"template arg {arg!r} references undefined step output 'steps.{path}' with no `| default(...)` fallback"
        )


def _find_missing_step_path(arg: str, steps_data: dict[str, Any]) -> str | None:
    """Return the first ``steps.X.Y`` path in ``arg`` that is unresolved.

    A path is unresolved when any segment is missing from ``steps_data`` or
    a non-leaf segment is not a dict. Returns None when every ``steps.*``
    reference in the arg resolves to a value.
    """
    for match in _STEP_PATH_RE.finditer(arg):
        path = match.group(1)
        node: Any = steps_data
        for part in path.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return path
        if node in (None, ""):
            return path
    return None


@dataclass
class StepResult:
    """Result of executing a single step.

    Attributes:
        name: Step name
        success: Whether the step succeeded (command + validations)
        exit_code: Command process exit code
        stdout: Command standard output
        stderr: Command standard error
        output: Parsed JSON output (if any)
        schema_name: Auto-detected schema name
        schema_valid: Whether output matched the schema
        schema_errors: Schema validation error messages
        validation_results: Results from bound validations
        error: Error message if step failed
    """

    name: str
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    output: dict[str, Any] | None = None
    schema_name: str | None = None
    schema_valid: bool = True
    schema_errors: list[str] = field(default_factory=list)
    validation_results: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


@dataclass
class StepResults:
    """Results of executing all steps.

    Attributes:
        success: Whether all steps succeeded
        steps: Results for each step
        accumulated_outputs: All step outputs merged
    """

    success: bool = True
    steps: list[StepResult] = field(default_factory=list)
    accumulated_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)

    def add_step(self, result: StepResult) -> None:
        """Add a step result and update overall success."""
        self.steps.append(result)
        if not result.success:
            self.success = False
        if result.output:
            self.accumulated_outputs[result.name] = result.output


class StepExecutor:
    """Executes steps sequentially.

    The executor:
    1. Runs each step's command
    2. Parses JSON output and validates against auto-detected schema
    3. Stores output in context for subsequent steps
    4. Continues or stops based on step configuration

    Validations are run separately after phases complete via run_validations_for_phase().
    """

    def __init__(self, working_dir: str | Path | None = None) -> None:
        """Initialize step executor.

        Args:
            working_dir: Default working directory for commands
        """
        self.working_dir = Path(working_dir) if working_dir else Path.cwd()

    def execute_steps(
        self,
        steps: list[StepConfig],
        context: Context,
        best_effort: bool = False,
    ) -> StepResults:
        """Execute all steps sequentially.

        Args:
            steps: List of step configurations
            context: Context for templating and storing outputs
            best_effort: When True, continue executing remaining steps even if
                one fails.  Used for teardown phases where all cleanup steps
                should be attempted regardless of individual failures.

        Returns:
            StepResults with all step outcomes
        """
        results = StepResults()

        for step in steps:
            if step.skip:
                logger.info(f"Skipping step '{step.name}' (skip: true) and its validations")
                results.add_step(
                    StepResult(
                        name=step.name,
                        success=True,
                        exit_code=0,
                        stdout="",
                        stderr="",
                        error="Step skipped",
                    )
                )
                continue

            logger.info(f"Executing step: {step.name}")
            step_result = self._execute_step(step, context)
            results.add_step(step_result)

            # Store output in context for subsequent steps
            if step_result.output:
                context.set_step_output(step.name, step_result.output)

            if not step_result.success and not step.continue_on_failure:
                if best_effort:
                    logger.warning(f"Step {step.name} failed (best-effort mode, continuing)")
                    results.success = False
                else:
                    logger.error(f"Step {step.name} failed, stopping execution")
                    results.success = False
                    break

        return results

    def run_validations_for_phase(
        self,
        phase: str,
        all_validations: dict[str, list[dict[str, Any]] | dict[str, Any]],
        context: Context,
        exclude_markers: list[str] | None = None,
        exclude_tests: list[str] | None = None,
        settings: dict[str, Any] | None = None,
        extra_pytest_args: list[str] | None = None,
        verbose: bool = False,
        junitxml: str | None = None,
        suite_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Run validations via pytest for a given phase.

        Uses native pytest for full pytest features (markers, filtering, fixtures)
        while capturing detailed results in-memory for rich output display.

        Determines when validations run based on (in priority order):
        1. Explicit `phase` field on the validation
        2. Inferred from `step` - uses the step's phase
        3. Default: 'test' phase

        Supports two config formats:
        1. List format (original):
           validations:
             category:
               - CheckName:
                   step: step_name
                   phase: setup

        2. Group defaults format (new):
           validations:
             category:
               step: step_name
               checks:
                 - CheckName:
                     other_param: value

        Args:
            phase: Current phase ('setup', 'test', 'teardown')
            all_validations: All validations from tests.validations (grouped by category)
            context: Context with accumulated step outputs and step phases
            exclude_markers: List of markers to exclude (e.g., ['workload', 'l2'])
            settings: Test settings dict (e.g., show_skipped_tests)
            extra_pytest_args: Pytest arguments (-k, -m, -v, etc.)
            verbose: Enable verbose output
            junitxml: Path to write JUnit XML report
            suite_name: Name for the JUnit XML test suite (e.g., phase name)

        Returns:
            List of validation results with name, passed, message, category
        """
        if not all_validations:
            return []

        try:
            from isvtest.main import run_validations_via_pytest

            step_outputs = context.get_accumulated_context().get("steps", {})
            step_phases = context.get_all_step_phases()

            # Render Jinja2 templates in validation parameters using context
            # This handles templates like {{ steps.setup.slurm.partitions.cpu.nodes | length }}
            rendered_validations = context.render_dict(all_validations)

            _exit_code, results = run_validations_via_pytest(
                validations=rendered_validations,
                step_outputs=step_outputs,
                step_phases=step_phases,
                phase=phase,
                extra_pytest_args=extra_pytest_args,
                exclude_markers=exclude_markers,
                exclude_tests=exclude_tests,
                settings=settings,
                verbose=verbose,
                junitxml=junitxml,
                suite_name=suite_name,
            )

            return results

        except ImportError as e:
            logger.error(f"Failed to import isvtest: {e}")
            logger.error("Cannot run validations without isvtest package")
            return []

    def _execute_step(self, step: StepConfig, context: Context) -> StepResult:
        """Execute a single step.

        Args:
            step: Step configuration
            context: Context for templating

        Returns:
            StepResult with command outcome
        """
        # Render args with accumulated context
        try:
            rendered_args = self._render_args(step.args, context)
        except MissingStepRefError as e:
            logger.warning(
                f"Skipping step '{step.name}': {e}. This typically means an upstream step failed or was skipped."
            )
            return StepResult(
                name=step.name,
                success=False,
                exit_code=-1,
                stdout="",
                stderr="",
                error=f"Skipped: missing step reference steps.{e.missing_path}",
            )

        # Normalize command - replace python/python3 with current interpreter
        # Also handle "uv run python3" pattern by stripping it
        command = step.command
        cmd_base_parts: list[str] = []

        if command.startswith("uv run python"):
            # Strip "uv run python" or "uv run python3" prefix, use current interpreter
            parts = shlex.split(command)  # ["uv", "run", "python3", "script.py"]
            if len(parts) >= 4:
                cmd_base_parts = [sys.executable, parts[3]]
            else:
                cmd_base_parts = [sys.executable]
        elif command.startswith("python3 ") or command.startswith("python "):
            # Replace python3/python with current interpreter
            parts = shlex.split(command)
            if len(parts) > 1:
                cmd_base_parts = [sys.executable] + parts[1:]
            else:
                cmd_base_parts = [sys.executable]
        else:
            # Non-Python command, keep as-is (may contain spaces, use shlex.split)
            cmd_base_parts = shlex.split(command)

        # Build full command
        cmd_parts = cmd_base_parts + rendered_args

        # Determine working directory
        cwd = Path(step.working_dir) if step.working_dir else self.working_dir

        # Build environment
        env = os.environ.copy()
        if step.env:
            env.update(step.env)

        # Log command with sensitive args masked
        masked_cmd = mask_sensitive_args(cmd_parts, step.sensitive_args)
        logger.info(f"Command: {masked_cmd}")
        logger.debug(f"Working directory: {cwd}")

        try:
            result = subprocess.run(
                cmd_parts,
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                timeout=step.timeout,
            )

            step_result = StepResult(
                name=step.name,
                success=result.returncode == 0,
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )

            # Always parse JSON output, even on failure - scripts output structured errors
            step_result = self._parse_output(step_result)

            if result.returncode != 0:
                # Use error from parsed output if available, otherwise generic message
                if step_result.output and step_result.output.get("error"):
                    error_type = step_result.output.get("error_type", "")
                    error_msg = step_result.output.get("error", "")
                    if error_type:
                        step_result.error = f"[{error_type}] {error_msg}"
                    else:
                        step_result.error = error_msg
                else:
                    step_result.error = f"Command exited with code {result.returncode}"
                    if result.stderr:
                        step_result.error += f": {result.stderr.strip()[:200]}"
                return step_result

            # Validate against explicit or auto-detected schema
            if step_result.output:
                step_result = self._validate_schema(step_result, step)

            return step_result

        except subprocess.TimeoutExpired as e:
            return StepResult(
                name=step.name,
                success=False,
                exit_code=-1,
                stdout=e.stdout if isinstance(e.stdout, str) else "",
                stderr=e.stderr if isinstance(e.stderr, str) else "",
                error=f"Command timed out after {step.timeout} seconds",
            )
        except FileNotFoundError:
            return StepResult(
                name=step.name,
                success=False,
                exit_code=-1,
                stdout="",
                stderr="",
                error=f"Command not found: {step.command}",
            )
        except Exception as e:
            return StepResult(
                name=step.name,
                success=False,
                exit_code=-1,
                stdout="",
                stderr="",
                error=f"Command execution failed: {e}",
            )

    def _render_args(self, args: list[str], context: Context) -> list[str]:
        """Render Jinja2 templates in command arguments.

        Args:
            args: List of argument strings (may contain {{ }} templates)
            context: Context with step outputs for rendering

        Returns:
            List of rendered argument strings (empty strings are filtered out
            only when the template used an explicit ``| default(...)`` fallback)

        Raises:
            MissingStepRefError: when an arg references ``{{steps.X.Y}}`` that
                is unresolved in the current context and has no ``default()``
                filter. This prevents silently producing malformed commands
                (e.g., ``teardown.py --vpc-id`` with no value) when upstream
                steps failed or were skipped.
        """
        env = _create_jinja_env()
        # Get full context including step outputs
        ctx_data = context.get_accumulated_context()
        steps_data = ctx_data.get("steps", {})
        rendered = []

        for arg in args:
            if "{{" in arg and "}}" in arg:
                try:
                    template = env.from_string(arg)
                    result = template.render(**ctx_data)
                except Exception as e:
                    logger.warning(f"Failed to render arg '{arg}': {e}")
                    rendered.append(arg)
                    continue

                if result.strip():
                    rendered.append(result)
                    continue

                # Empty result: distinguish "explicit default(''/None)" from
                # "silently-missing step output". The latter is an error —
                # surface it so the caller can skip the step cleanly instead
                # of invoking the command with a stripped-out required arg.
                if "default(" in arg:
                    continue
                missing = _find_missing_step_path(arg, steps_data)
                if missing:
                    raise MissingStepRefError(arg, missing)
            else:
                rendered.append(arg)

        return rendered

    def _parse_output(self, result: StepResult) -> StepResult:
        """Parse JSON output from command stdout.

        Args:
            result: StepResult with stdout to parse

        Returns:
            Updated StepResult with parsed output or error
        """
        stdout = result.stdout.strip()
        if not stdout:
            # No output is okay for some steps (like teardown)
            return result

        try:
            result.output = json.loads(stdout)
        except json.JSONDecodeError as e:
            # Not all commands produce JSON - this is okay
            logger.debug(f"Output is not JSON for step {result.name}: {e}")

        return result

    def _validate_schema(self, result: StepResult, step: StepConfig) -> StepResult:
        """Validate output against explicit or auto-detected schema.

        Schema resolution order:
        1. Explicit step.output_schema (if provided)
        2. Auto-detect from step.name
        3. Fallback to "generic"

        Args:
            result: StepResult with parsed output
            step: Step configuration

        Returns:
            Updated StepResult with schema validation results
        """
        # Use explicit schema if provided, otherwise auto-detect
        if step.output_schema:
            schema_name = step.output_schema
            logger.debug(f"Using explicit schema '{schema_name}' for step: {step.name}")
        else:
            schema_name = get_schema_for_step(step.name)
            logger.debug(f"Auto-detected schema '{schema_name}' for step: {step.name}")

        result.schema_name = schema_name

        if schema_name is None:
            # No schema validation
            return result

        if result.output is None:
            # No output to validate
            return result

        is_valid, errors = validate_output(result.output, schema_name)
        result.schema_valid = is_valid
        result.schema_errors = errors

        if not is_valid:
            logger.error(f"Schema validation failed for step '{step.name}': {errors}")
            # Schema validation failure is an error - mark step as failed
            # Downstream steps/validations depend on correct output structure
            result.success = False

        return result
