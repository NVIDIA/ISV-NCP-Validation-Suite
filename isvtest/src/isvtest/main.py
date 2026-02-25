"""Main CLI entry point for nv-isv-test.

Note: For cluster lifecycle management, use isvctl instead:
    isvctl test run -f isvctl/configs/k8s.yaml
"""

import json
import os
import tempfile
from enum import Enum
from pathlib import Path
from typing import Annotated, Any

import pytest
import typer
from isvreporter.version import get_version

from isvtest.config.loader import ConfigLoader
from isvtest.core import runners as reframe_runner
from isvtest.core.logger import setup_logger
from isvtest.tests.test_validations import ADAPTER_HANDLED_CATEGORIES

logger = setup_logger()


def run_validations_via_pytest(
    validations: dict[str, list[dict[str, Any]] | dict[str, Any]],
    step_outputs: dict[str, dict[str, Any]],
    step_phases: dict[str, str] | None = None,
    phase: str = "test",
    extra_pytest_args: list[str] | None = None,
    exclude_markers: list[str] | None = None,
    settings: dict[str, Any] | None = None,
    verbose: bool = False,
    junitxml: str | None = None,
    suite_name: str | None = None,
) -> tuple[int, list[dict[str, Any]]]:
    """Run validations via pytest with step outputs available as context.

    This function bridges step-based execution with pytest-based validation.
    It transforms the new config format (tests.validations) into a format
    pytest can use, and passes step outputs for template rendering.

    Results are captured in-memory via test_validations module, giving you
    both full pytest features AND detailed validation messages.

    Args:
        validations: Validation config from tests.validations, grouped by category.
            Format: {category: [{CheckName: {params...}}, ...] | {step, phase, checks}}
        step_outputs: Accumulated step outputs from previous phases.
            Format: {step_name: {output_dict}}
        step_phases: Mapping of step names to their phases (for phase inference).
            Format: {step_name: phase}
        phase: Current phase to run validations for (filters by phase field).
        extra_pytest_args: Additional pytest arguments (-k, -m, -v, etc.).
        exclude_markers: Markers to exclude from validation runs.
        settings: Test settings dict (e.g., show_skipped_tests).
        verbose: Enable verbose output.
        junitxml: Path to write JUnit XML report.
        suite_name: Name for the JUnit XML test suite (defaults to pytest's "pytest").

    Returns:
        Tuple of (exit_code, validation_results).
        exit_code: 0 if all validations passed, non-zero otherwise.
        validation_results: List of validation result dicts with name, passed, message, category.
    """
    # Import result storage from test_validations
    from isvtest.tests.test_validations import clear_validation_results, get_validation_results

    # Transform validations into the format expected by test_validations.py
    # The test_validations.py expects a "validations" dict at config root
    transformed_validations = _transform_validations_for_pytest(validations, step_outputs, step_phases or {}, phase)

    if not transformed_validations:
        logger.info(f"No validations to run for phase '{phase}'")
        return 0, []

    # Build inventory by merging step outputs
    # This allows templates like {{ inventory.kubernetes.runtime_class }} to work
    # by extracting platform sections (kubernetes, slurm, etc.) from step outputs
    inventory: dict[str, Any] = {"steps": step_outputs}  # Keep steps available too
    logger.debug(f"Building inventory from step_outputs: {list(step_outputs.keys())}")
    for step_name, output in step_outputs.items():
        logger.debug(f"Step '{step_name}' output keys: {list(output.keys()) if output else 'None'}")
        for key, value in output.items():
            if isinstance(value, dict):
                # Merge nested dicts (e.g., kubernetes, slurm sections)
                if key not in inventory:
                    inventory[key] = {}
                if isinstance(inventory[key], dict):
                    inventory[key].update(value)
                    logger.debug(f"Merged '{key}' section with {len(value)} keys")
            else:
                # Top-level fields go to inventory root
                inventory[key] = value

    # Create a temporary config file with transformed validations
    temp_config: dict[str, Any] = {
        "validations": {"phase_validations": transformed_validations},
        "inventory": inventory,
    }

    # Include exclude markers so conftest.py can filter tests by marker
    if exclude_markers:
        temp_config["exclude"] = {"markers": exclude_markers}

    # Include settings (e.g., show_skipped_tests)
    if settings:
        temp_config["settings"] = settings

    # Create temp file for the config
    # Use JSON format (valid YAML) to avoid YAML's quote escaping issues that break
    # Jinja2 template parsing (single quotes become ''nvidia'', backslashes added)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        json.dump(temp_config, f, indent=2)
        temp_config_path = f.name

    try:
        # Get the tests directory relative to this module
        tests_dir = Path(__file__).parent / "tests"

        pytest_args = [
            str(tests_dir / "test_validations.py"),
            f"--rootdir={tests_dir}",
            "-o",
            "cache_dir=.pytest_cache",
            "--tb=short",
            "--config",
            temp_config_path,
        ]

        if verbose:
            pytest_args.insert(1, "--verbose")

        if junitxml:
            pytest_args.extend(["--junitxml", junitxml])

        if suite_name:
            pytest_args.extend(["-o", f"junit_suite_name={suite_name}"])

        # Note: exclude_markers from YAML are handled by conftest.py which reads them
        # directly from the config file. We don't add them as -m args here because
        # that would trigger conftest.py's "explicit marker selection" detection.

        # Add extra pytest args
        if extra_pytest_args:
            pytest_args.extend(extra_pytest_args)

        # Clear previous results before running
        clear_validation_results()

        logger.info(f"Running validations via pytest: {' '.join(pytest_args)}")
        exit_code = pytest.main(pytest_args)

        # Get detailed results captured during test execution
        results = get_validation_results()

        if not results and extra_pytest_args:
            k_filters = [
                extra_pytest_args[i + 1]
                for i, a in enumerate(extra_pytest_args)
                if a == "-k" and i + 1 < len(extra_pytest_args)
            ]
            if k_filters:
                logger.warning(
                    f"No tests matched -k '{k_filters[0]}' — check spelling or run without -k to see available tests"
                )

        return exit_code, results

    finally:
        # Clean up temp file
        try:
            os.unlink(temp_config_path)
        except OSError:
            pass


def _transform_validations_for_pytest(
    validations: dict[str, list[dict[str, Any]] | dict[str, Any]],
    step_outputs: dict[str, dict[str, Any]],
    step_phases: dict[str, str],
    phase: str,
) -> list[dict[str, Any]]:
    """Transform new-format validations into pytest-compatible format.

    The new format supports:
    - step: shorthand for referencing step output
    - phase: explicit phase filtering (or inferred from step's phase)
    - checks: list of validation checks

    Phase determination priority:
    1. Explicit `phase` field on the validation
    2. Inferred from `step` - uses the step's phase from step_phases
    3. Default: 'test' phase

    The pytest format expects:
    - List of {ValidationName: {params with step_output resolved}}

    Args:
        validations: New-format validations grouped by category
        step_outputs: Step outputs for resolving step references
        step_phases: Mapping of step names to their phases
        phase: Current phase to filter validations for

    Returns:
        List of validation dicts in pytest-compatible format
    """
    result = []

    for category, category_config in validations.items():
        if category in ADAPTER_HANDLED_CATEGORIES:
            continue

        # Determine format: group defaults or list
        if isinstance(category_config, dict) and "checks" in category_config:
            # Group defaults format
            group_step = category_config.get("step")
            group_phase = category_config.get("phase")  # Don't default - let inference handle it
            checks = category_config.get("checks", [])
        elif isinstance(category_config, list):
            # List format
            group_step = None
            group_phase = None
            checks = category_config
        else:
            logger.warning(f"Unknown validation format for category '{category}'")
            continue

        for check in checks:
            for name, params in check.items():
                if params is None:
                    params = {}

                # Apply group defaults
                if group_step and "step" not in params:
                    params = {"step": group_step, **params}
                if group_phase and "phase" not in params:
                    params = {"phase": group_phase, **params}

                # Determine validation phase (priority: explicit > infer from step > default)
                # If a step is referenced but has no registered phase, it was skipped
                if "phase" in params:
                    validation_phase = params["phase"]
                elif "step" in params:
                    step_name = params["step"]
                    if step_name not in step_phases:
                        logger.info(f"Skipping validation '{name}' in [{category}]: step '{step_name}' is skipped")
                        continue
                    validation_phase = step_phases[step_name]
                else:
                    validation_phase = "test"  # Default to test phase

                # Filter by phase
                if validation_phase != phase:
                    continue

                # Resolve step to actual step output
                resolved_params = dict(params)
                if "step" in resolved_params:
                    step_name = resolved_params.pop("step")
                    step_output = step_outputs.get(step_name, {})
                    resolved_params["step_output"] = step_output

                # Remove phase from params (not needed by validation)
                resolved_params.pop("phase", None)

                # Add category for result reporting
                resolved_params["_category"] = category

                result.append({name: resolved_params})

    return result


class Platform(str, Enum):
    """Supported platforms for validation."""

    ALL = "all"
    BARE_METAL = "bare_metal"
    KUBERNETES = "kubernetes"
    K8S = "kubernetes"  # Alias for kubernetes
    SLURM = "slurm"
    COMMON = "common"


def run_pytest_tests(
    platform: str | None = None,
    config_file: str | None = None,
    inventory_path: str | None = None,
    markers: list[str] | None = None,
    verbose: bool = False,
    extra_pytest_args: list[str] | None = None,
) -> int:
    """Run pytest-based tests.

    Args:
        platform: Platform to validate (bare_metal, kubernetes, slurm, common, or all)
        config_file: Direct path to cluster configuration file
        inventory_path: Path to cluster inventory file (JSON or YAML)
        markers: Pytest markers to filter tests (e.g., ['gpu', 'network'])
        verbose: Show verbose output
        extra_pytest_args: Additional arguments to pass to pytest

    Returns:
        Exit code (0 = success, non-zero = failure)
    """
    # Load config and apply env_vars
    config = None
    if config_file:
        try:
            config = ConfigLoader().load_cluster_config(
                config_file=config_file,
                inventory_path=inventory_path,
            )
        except FileNotFoundError as e:
            error_msg = str(e)
            if "Inventory file not found" in error_msg:
                logger.error(f"Inventory error: {error_msg}")
            else:
                logger.error(f"Configuration file '{config_file}' not found: {error_msg}")
            return 1

    # Apply env_vars from config (only if not already set in environment)
    if config:
        env_vars = config.get("env_vars", {}) or {}
        for key, value in env_vars.items():
            if key not in os.environ:
                logger.info(f"Setting {key}={value} from config")
                os.environ[key] = str(value)
            else:
                logger.debug(f"Using existing {key}={os.environ[key]} (overrides config)")

    # Get the tests directory relative to this module
    tests_dir = Path(__file__).parent / "tests"

    pytest_args = [
        str(tests_dir),
        f"--rootdir={tests_dir}",  # Clean path display (avoid ../../../)
        "-o",
        "cache_dir=.pytest_cache",  # Writable cache in cwd (not installed package)
        "--tb=short",
        "--junitxml=junit-validation.xml",
    ]

    # Only add verbosity flag if explicitly requested
    if verbose:
        pytest_args.insert(1, "--verbose")

    # Add config file
    if config_file:
        pytest_args.extend(["--config", config_file])

    # Add inventory path if specified
    if inventory_path:
        pytest_args.extend(["--inventory", inventory_path])

    # Add platform marker if specified
    if platform and platform != "all":
        normalized_platform = "bare_metal" if platform == "common" else platform
        if normalized_platform in ["bare_metal", "kubernetes", "slurm"]:
            pytest_args.extend(["-m", normalized_platform])

    # Add markers
    if markers:
        for marker in markers:
            pytest_args.extend(["-m", marker])

    # Add any extra pytest arguments
    if extra_pytest_args:
        pytest_args.extend(extra_pytest_args)

    logger.info(f"Running tests: {' '.join(pytest_args)}")
    return pytest.main(pytest_args)


app = typer.Typer(
    name="isvtest",
    help="NVIDIA ISV Lab validation tests",
    no_args_is_help=True,
    add_completion=False,
)


@app.command("test", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def test_cmd(
    ctx: typer.Context,
    platform: Annotated[
        Platform,
        typer.Option(
            "--platform",
            "-p",
            help="Platform to test",
        ),
    ] = Platform.ALL,
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-f",
            help="Path to test configuration file (YAML)",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
    ] = None,
    markers: Annotated[
        list[str] | None,
        typer.Option(
            "--markers",
            "-m",
            help="Pytest markers to filter tests (can be repeated)",
        ),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Show detailed output for each test",
        ),
    ] = False,
) -> None:
    """Run validation tests.

    Examples:
        isvtest test --config /path/to/tests.yaml

        isvtest test --platform bare_metal --config tests.yaml

        isvtest test --config tests.yaml --markers gpu --markers network

        isvtest test --config tests.yaml -k test_gpu --maxfail=1
    """
    # Extra args after -- are passed to pytest
    extra_args = list(ctx.args)

    exit_code = run_pytest_tests(
        platform=platform.value,
        config_file=str(config) if config else None,
        markers=markers,
        verbose=verbose,
        extra_pytest_args=extra_args,
    )
    raise typer.Exit(code=exit_code)


@app.command("workload")
def workload(
    tags: Annotated[
        list[str] | None,
        typer.Option(
            "--tags",
            "-t",
            help="Tags to filter workload tests (can be repeated)",
        ),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Show detailed output",
        ),
    ] = False,
) -> None:
    """Run ReFrame workload tests.

    Examples:
        isvtest workload --tags gpu --tags cuda

        isvtest workload --tags nccl
    """
    if verbose:
        logger.info("Running workload tests with verbose output")

    results = reframe_runner.run_reframe_tests(tags=tags)
    raise typer.Exit(code=0 if results["success"] else 1)


def _version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        typer.echo(f"isvtest {get_version('isvtest')}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def callback(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option("--version", "-V", help="Show version and exit.", callback=_version_callback, is_eager=True),
    ] = False,
) -> None:
    """NVIDIA ISV Lab validation tests.

    For full cluster lifecycle management, use isvctl:
        isvctl test run -f isvctl/configs/k8s.yaml
    """
    if ctx.invoked_subcommand is None:
        ctx.invoke(test_cmd)


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
