"""Main orchestration loop for isvctl.

This module implements the test lifecycle using step-based execution:
1. Execute steps grouped by phase (defined in config's `phases` list)
2. Run validations after each phase
"""

import logging
import shutil
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from isvctl.config.schema import RunConfig
from isvctl.orchestrator.commands import CommandExecutor
from isvctl.orchestrator.context import Context
from isvctl.orchestrator.step_executor import StepExecutor, StepResults
from isvctl.redaction import redact_dict, redact_junit_xml_tree

logger = logging.getLogger(__name__)


class Phase(str, Enum):
    """Test lifecycle phases."""

    ALL = "all"
    SETUP = "setup"
    TEST = "test"
    TEARDOWN = "teardown"


@dataclass
class PhaseResult:
    """Result of a single phase execution.

    Attributes:
        phase: Which phase was executed
        success: Whether the phase succeeded
        message: Human-readable status message
        details: Additional details (command output, test results, etc.)
    """

    phase: Phase
    success: bool
    message: str
    details: dict[str, Any] | None = None


@dataclass
class OrchestratorResult:
    """Result of the full orchestration run.

    Attributes:
        success: Whether all phases succeeded
        phases: Results for each phase that was executed
        inventory: Final inventory data (step outputs)
    """

    success: bool
    phases: list[PhaseResult]
    inventory: dict[str, Any] | None = None


def _merge_junit_xmls(phase_files: list[Path], output_path: Path) -> None:
    """Merge multiple per-phase JUnit XML files into a single file.

    Combines all <testsuite> elements from each phase file into a single
    <testsuites> root element. This allows multi-phase orchestration runs
    to produce a single comprehensive JUnit XML report.

    Args:
        phase_files: List of per-phase JUnit XML file paths
        output_path: Final output path for the merged XML
    """
    root = ET.Element("testsuites")
    root.set("name", "isvctl validation tests")

    for phase_file in phase_files:
        if not phase_file.exists():
            continue
        try:
            tree = ET.parse(phase_file)
            phase_root = tree.getroot()
            # Handle both <testsuites><testsuite>... and direct <testsuite>
            if phase_root.tag == "testsuites":
                for suite in phase_root:
                    root.append(suite)
            elif phase_root.tag == "testsuite":
                root.append(phase_root)
        except ET.ParseError:
            logger.warning(f"Failed to parse JUnit XML: {phase_file}")
            continue

    redact_junit_xml_tree(root)

    tree = ET.ElementTree(root)
    ET.indent(tree, space="    ")
    tree.write(str(output_path), encoding="utf-8", xml_declaration=True)
    logger.info(f"JUnit XML report written to: {output_path}")


class Orchestrator:
    """Orchestrates the full test lifecycle using step-based execution.

    The orchestrator:
    1. Executes steps grouped by phase (in order defined by config's `phases` list)
    2. Runs validations after each phase
    3. Handles failure and teardown logic
    """

    def __init__(
        self,
        config: RunConfig,
        working_dir: str | Path | None = None,
    ) -> None:
        """Initialize orchestrator.

        Args:
            config: Merged test run configuration
            working_dir: Working directory for command execution
        """
        self.config = config
        self.context = Context(config)
        self.executor = CommandExecutor(working_dir=working_dir)
        self.step_executor = StepExecutor(working_dir=working_dir)
        self._results: list[PhaseResult] = []
        # Validation options (set in run())
        self._extra_pytest_args: list[str] | None = None
        self._verbose: bool = False
        self._junitxml: str | None = None

    def run(
        self,
        phases: list[Phase] | None = None,
        teardown_on_failure: bool = True,
        extra_pytest_args: list[str] | None = None,
        verbose: bool = False,
        junitxml: str | None = None,
    ) -> OrchestratorResult:
        """Run the test lifecycle.

        Args:
            phases: Specific phases to run (default: all)
            teardown_on_failure: Run teardown even if earlier phases fail
            extra_pytest_args: Pytest arguments for validations (-k, -m, -v, etc.)
                - `-k AccessKey`: Run only validations matching "AccessKey"
                - `-m kubernetes`: Run only validations with kubernetes marker
            verbose: Enable verbose output for validations
            junitxml: Path to write JUnit XML report for validations

        Returns:
            OrchestratorResult with phase results
        """
        if phases is None:
            phases = [Phase.SETUP, Phase.TEST, Phase.TEARDOWN]

        self._results = []
        self._extra_pytest_args = extra_pytest_args
        self._verbose = verbose
        self._junitxml = junitxml

        # Determine platform from test config
        platform = self._detect_platform()
        if not platform:
            return OrchestratorResult(
                success=False,
                phases=[
                    PhaseResult(
                        phase=Phase.SETUP,
                        success=False,
                        message="Cannot determine platform from configuration",
                    )
                ],
            )

        logger.info(f"Starting orchestration for platform: {platform}")

        return self._run_steps_mode(platform, phases, teardown_on_failure)

    def _run_steps_mode(
        self,
        platform: str,
        requested_phases: list[Phase],
        teardown_on_failure: bool,
    ) -> OrchestratorResult:
        """Run orchestration using the steps mode with phase-based validations.

        Phases are defined in the config's `phases` list and executed in that order.
        For each phase:
        1. Execute all steps with that phase
        2. Run all validations matching that phase (inferred from step or default to test)

        Args:
            platform: Target platform
            requested_phases: CLI-requested phases (for filtering)
            teardown_on_failure: Whether to run teardown on failure

        Returns:
            OrchestratorResult with step outcomes
        """
        logger.info(f"Running in steps mode for platform: {platform}")

        steps = self.config.get_steps(platform)
        if not steps:
            return OrchestratorResult(
                success=False,
                phases=[
                    PhaseResult(
                        phase=Phase.SETUP,
                        success=False,
                        message=f"No steps defined for platform: {platform}",
                    )
                ],
            )

        # Get phases from config (defines execution order)
        config_phases = self.config.get_phases(platform)
        logger.info(f"Configured phases: {config_phases}")

        # Validate all steps have a phase in the config phases list
        for step in steps:
            step_phase = (step.phase or "setup").lower()
            if step_phase not in config_phases:
                return OrchestratorResult(
                    success=False,
                    phases=[
                        PhaseResult(
                            phase=Phase.SETUP,
                            success=False,
                            message=f"Step '{step.name}' has phase '{step_phase}' not in phases list: {config_phases}",
                        )
                    ],
                )

        # Group steps by phase
        steps_by_phase: dict[str, list] = {phase: [] for phase in config_phases}
        for step in steps:
            step_phase = (step.phase or "setup").lower()
            steps_by_phase[step_phase].append(step)

        # Register step phases upfront so validation phase inference works
        # even before a step has executed. Skipped steps are excluded so
        # their validations are also skipped automatically.
        for step in steps:
            if step.skip:
                continue
            step_phase = (step.phase or "setup").lower()
            self.context.set_step_phase(step.name, step_phase)

        # Get all validations from config
        all_validations = {}
        if self.config.tests and self.config.tests.validations:
            all_validations = self.config.tests.validations

        # Get exclude markers for filtering validation categories
        exclude_markers: list[str] = []
        if self.config.tests and self.config.tests.exclude:
            exclude_markers = self.config.tests.exclude.get("markers", [])

        phase_results: list[PhaseResult] = []
        overall_success = True
        setup_succeeded = False  # Track setup phase specifically

        # Build set of requested phase names for filtering
        requested_phase_names = {p.value for p in requested_phases}

        # Per-phase JUnit XML: use temp files per phase, merge at the end
        # This prevents later phases from overwriting earlier phases' results
        junit_tmpdir: str | None = None
        phase_junit_files: list[Path] = []

        try:
            if self._junitxml:
                junit_tmpdir = tempfile.mkdtemp(prefix="junit-phases-")

            # Execute phases in configured order
            for phase_name in config_phases:
                # Skip phases not in requested_phases (don't add to results at all)
                if phase_name not in requested_phase_names and Phase.ALL not in requested_phases:
                    continue
                phase_steps = steps_by_phase.get(phase_name, [])

                # Map phase name to Phase enum for display (setup/teardown are special)
                if phase_name == "setup":
                    phase_enum = Phase.SETUP
                elif phase_name == "teardown":
                    phase_enum = Phase.TEARDOWN
                else:
                    phase_enum = Phase.TEST  # Use TEST for display of custom phases

                # Check if this phase should run
                is_teardown = phase_name == "teardown"
                skip_reason: str | None = None

                # Skip non-teardown phases if previous phase failed
                if not overall_success and not is_teardown:
                    skip_reason = "previous phase failed"

                # Skip teardown if setup failed (teardown depends on setup outputs)
                # or if teardown_on_failure is False
                if is_teardown:
                    if not setup_succeeded:
                        skip_reason = "setup phase did not succeed"
                    elif not overall_success and not teardown_on_failure:
                        skip_reason = "teardown_on_failure is disabled"

                if skip_reason:
                    logger.info(f"Skipping {phase_name}: {skip_reason}")
                    # Add a skipped phase result for visibility
                    phase_results.append(
                        PhaseResult(
                            phase=phase_enum,
                            success=True,  # Skipped is not a failure
                            message=f"SKIPPED: {skip_reason}",
                        )
                    )
                    continue

                # Execute steps for this phase
                if phase_steps:
                    step_results = self.step_executor.execute_steps(phase_steps, self.context)
                else:
                    step_results = StepResults()

                # Use a per-phase temp file for JUnit XML to avoid overwriting
                phase_junitxml: str | None = None
                if junit_tmpdir:
                    phase_junitxml = str(Path(junit_tmpdir) / f"junit-{phase_name}.xml")

                # Run validations for this phase (excluding categories that match exclude markers)
                test_settings = self.config.tests.settings if self.config.tests else {}
                phase_validations = self.step_executor.run_validations_for_phase(
                    phase_name,
                    all_validations,
                    self.context,
                    exclude_markers=exclude_markers,
                    settings=test_settings,
                    extra_pytest_args=self._extra_pytest_args,
                    verbose=self._verbose,
                    junitxml=phase_junitxml,
                    suite_name=f"{platform}/{phase_name}",
                )

                # Collect per-phase JUnit XML if it was generated
                if phase_junitxml and Path(phase_junitxml).exists():
                    phase_junit_files.append(Path(phase_junitxml))

                # Only add phase result if there were steps or validations
                if phase_steps or phase_validations:
                    phase_results.append(
                        self._create_phase_result(phase_enum, step_results, phase_validations, phase_name)
                    )

                # Update success status
                phase_success = step_results.success and all(v.get("passed", False) for v in phase_validations)
                if not phase_success:
                    overall_success = False

                # Track setup success for teardown decision
                if phase_name == "setup" and phase_success:
                    setup_succeeded = True

            # Merge per-phase JUnit XMLs into the final output file
            if self._junitxml and phase_junit_files:
                _merge_junit_xmls(phase_junit_files, Path(self._junitxml))

        finally:
            # Clean up temp directory
            if junit_tmpdir:
                shutil.rmtree(junit_tmpdir, ignore_errors=True)

        return OrchestratorResult(
            success=overall_success,
            phases=phase_results,
            inventory=self.context.get_accumulated_context().get("steps", {}),
        )

    def _create_phase_result(
        self,
        phase: Phase,
        step_results: StepResults,
        validation_results: list[dict],
        phase_name: str | None = None,
    ) -> PhaseResult:
        """Create a PhaseResult from step execution and validation results.

        Args:
            phase: The phase enum for display
            step_results: Results from step execution
            validation_results: Results from phase validations
            phase_name: Custom phase name (for non-standard phases)

        Returns:
            PhaseResult for the phase
        """
        display_name = phase_name or phase.value

        # Build step messages
        step_messages = [f"{s.name}: {'passed' if s.success else 'failed'}" for s in step_results.steps]

        # Check if any validations failed
        validation_failures = [v for v in validation_results if not v.get("passed", False)]
        all_validations_passed = len(validation_failures) == 0

        # Overall phase success
        phase_success = step_results.success and all_validations_passed

        # Build message
        if step_messages:
            message = "; ".join(step_messages)
        else:
            message = f"{display_name} phase completed"

        return PhaseResult(
            phase=phase,
            success=phase_success,
            message=message,
            details={
                "steps": [
                    {
                        "name": s.name,
                        "success": s.success,
                        "error": s.error,
                        "output": redact_dict(s.output),
                        "schema_name": s.schema_name,
                        "schema_valid": s.schema_valid,
                        "schema_errors": s.schema_errors,
                    }
                    for s in step_results.steps
                ],
                "validations": validation_results,
            },
        )

    def _detect_platform(self) -> str | None:
        """Detect platform from configuration.

        Checks multiple locations for platform:
        1. tests.platform (isvctl schema)
        2. Root-level platform (legacy isvtest schema)

        Returns:
            Platform string (e.g., 'kubernetes', 'slurm', 'bare_metal') or None
        """
        platform = None

        # Check isvctl schema location first
        if self.config.tests and self.config.tests.platform:
            platform = self.config.tests.platform
        # Fall back to root-level platform (legacy isvtest configs)
        elif hasattr(self.config, "model_extra") and self.config.model_extra:
            platform = self.config.model_extra.get("platform")

        if platform:
            # Normalize 'k8s' to 'kubernetes'
            if platform == "k8s":
                return "kubernetes"
            return platform
        return None
