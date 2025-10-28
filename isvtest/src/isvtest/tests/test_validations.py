import sys
from difflib import get_close_matches
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from isvtest.config.loader import ConfigLoader
from isvtest.core.discovery import discover_tests
from isvtest.core.runners import LocalRunner
from isvtest.core.validation import BaseValidation

if TYPE_CHECKING:
    from isvtest.testing.subtests import SubTests

# Categories handled by specialized adapters (not standard BaseValidation discovery)
ADAPTER_HANDLED_CATEGORIES = {"reframe"}

# In-memory storage for validation results (used by isvctl integration)
# This allows capturing detailed results without temp files
_validation_results: list[dict[str, Any]] = []


def get_validation_results() -> list[dict[str, Any]]:
    """Get captured validation results from the last pytest run."""
    return _validation_results.copy()


def clear_validation_results() -> None:
    """Clear captured validation results before a new pytest run."""
    _validation_results.clear()


def _suggest_similar_tests(name: str, available: list[str], max_suggestions: int = 3) -> list[str]:
    """Find test names similar to the given name."""
    # Try difflib for fuzzy matching
    matches = get_close_matches(name, available, n=max_suggestions, cutoff=0.4)
    if matches:
        return matches

    # Fallback: find tests with matching prefix (e.g., "Bm" -> BmDriverVersion, BmCudaVersion)
    prefix = ""
    for i, char in enumerate(name):
        if char.isupper() and i > 0:
            prefix = name[:i]
            break
    if prefix:
        prefix_matches = [t for t in available if t.startswith(prefix)][:max_suggestions]
        if prefix_matches:
            return prefix_matches

    return []


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Generate tests for all BaseValidation and BaseWorkloadCheck subclasses."""
    if "validation_class" in metafunc.fixturenames and "validation_config" in metafunc.fixturenames:
        # Discover validations in isvtest/validations
        validations_dir = Path(__file__).parent.parent / "validations"
        test_classes = list(discover_tests(validations_dir, "isvtest.validations"))

        # Discover workloads in isvtest/workloads
        workloads_dir = Path(__file__).parent.parent / "workloads"
        if workloads_dir.exists():
            test_classes.extend(list(discover_tests(workloads_dir, "isvtest.workloads")))

        if not test_classes:
            return

        # Load configuration if available
        enabled_validations_config = {}
        cluster_inventory: dict[str, Any] = {}
        filtering_enabled = False
        show_skipped = False

        try:
            config_file_arg = metafunc.config.getoption("--config", default=None)
            inventory_arg = metafunc.config.getoption("--inventory", default=None)

            if config_file_arg:
                filtering_enabled = True
                loader = ConfigLoader()
                cluster_config = loader.load_cluster_config(
                    config_file=config_file_arg,
                    inventory_path=inventory_arg,
                )
                # Extract inventory - contains dynamic info about resources created during setup
                # (e.g., instance IPs, SSH keys) needed by remote validations like AWS EC2
                cluster_inventory = cluster_config.get("inventory", {})
                # Get all validation categories, excluding adapter-handled ones
                all_categories = list((cluster_config.get("validations") or {}).keys())
                standard_categories = [c for c in all_categories if c not in ADAPTER_HANDLED_CATEGORIES]
                enabled_validations_config = loader.get_all_validations(cluster_config, categories=standard_categories)
                # Check if we should show skipped tests
                show_skipped = cluster_config.get("settings", {}).get("show_skipped_tests", False)
        except (ImportError, FileNotFoundError, ValueError, AttributeError, OSError):
            pass

        # Create parameters with markers
        params = []
        ids = []

        # Map class names to classes for easier lookup
        test_classes_map = {cls.__name__: cls for cls in test_classes}
        processed_classes = set()
        unmatched_validations = []

        if filtering_enabled:
            # 1. Process configured validations (including aliases/variants)
            for validation_name, validation_config in enabled_validations_config.items():
                target_class = None

                # Exact match
                if validation_name in test_classes_map:
                    target_class = test_classes_map[validation_name]
                else:
                    # Suffix match (e.g. ClassName-Variant)
                    # Find longest matching class name prefix to handle potential overlaps
                    possible_matches = [name for name in test_classes_map.keys() if validation_name.startswith(name)]
                    if possible_matches:
                        longest_match = max(possible_matches, key=len)
                        # Verify it is a valid variant (starts with name + separator)
                        # We accept - or _ as separator
                        if validation_name.startswith(f"{longest_match}-") or validation_name.startswith(
                            f"{longest_match}_"
                        ):
                            target_class = test_classes_map[longest_match]

                if target_class:
                    processed_classes.add(target_class.__name__)

                    # Get markers from class, ensuring we handle inheritance correctly
                    markers = getattr(target_class, "markers", [])
                    pytest_marks = [getattr(pytest.mark, m) for m in markers]

                    # Merge inventory into validation config for validations that need it.
                    # Most validations (k8s, slurm, bare_metal) run commands locally and don't need inventory.
                    # Remote validations (e.g., AWS EC2) need inventory to get connection info
                    # (instance IP, SSH key path) for resources created during setup.
                    merged_config = {**validation_config, "inventory": cluster_inventory}
                    params.append(pytest.param(target_class, merged_config, validation_name, marks=pytest_marks))
                    ids.append(validation_name)
                else:
                    # Track unmatched validations for warning
                    unmatched_validations.append(validation_name)

            # Warn about configured validations that don't match any test class
            if unmatched_validations:
                available_tests = sorted(test_classes_map.keys())
                for validation_name in unmatched_validations:
                    similar = _suggest_similar_tests(validation_name, available_tests)
                    if similar:
                        hint = f"Did you mean: {', '.join(similar)}?"
                    else:
                        hint = "Check spelling or run without --config to see all available tests."
                    print(
                        f"WARNING: Validation not found: '{validation_name}'. {hint}",
                        file=sys.stderr,
                    )

            # 2. Add skipped tests for classes NOT in config (if show_skipped)
            if show_skipped:
                for cls_name, cls in test_classes_map.items():
                    # If class was not processed (no exact or variant match found in config)
                    # We treat it as skipped.
                    if cls_name not in processed_classes:
                        markers = getattr(cls, "markers", [])
                        pytest_marks = [getattr(pytest.mark, m) for m in markers]
                        pytest_marks.append(pytest.mark.skip(reason="Not configured in cluster YAML"))

                        # Include inventory even for skipped tests (for consistency)
                        merged_config = {"inventory": cluster_inventory}
                        params.append(pytest.param(cls, merged_config, cls_name, marks=pytest_marks))
                        ids.append(cls_name)
        else:
            # No filtering, run all discovered tests with empty config
            for cls in test_classes:
                markers = getattr(cls, "markers", [])
                pytest_marks = [getattr(pytest.mark, m) for m in markers]
                params.append(pytest.param(cls, {"inventory": cluster_inventory}, cls.__name__, marks=pytest_marks))
                ids.append(cls.__name__)

        # Parametrize the test function with the discovered classes
        # Added validation_name to the parametrization to support variants
        if params:
            metafunc.parametrize("validation_class,validation_config,validation_name", params, ids=ids)
        else:
            # If no validations are configured/enabled, we must still parametrize arguments
            # to avoid "fixture not found" errors. We use a specific ID that will be
            # filtered out by pytest_collection_modifyitems in conftest.py.
            metafunc.parametrize(
                "validation_class,validation_config,validation_name",
                [(BaseValidation, {}, "no_validations")],
                ids=["NO_VALIDATIONS"],
            )


def test_validation(
    validation_class: type[BaseValidation],
    validation_config: dict[str, Any],
    validation_name: str,
    subtests: "SubTests",
) -> None:
    """Run an ISV validation test.

    Args:
        validation_class: The validation class to instantiate and run.
        validation_config: Configuration dictionary for the validation (includes inventory).
        validation_name: Display name for the validation (may include variant suffix).
        subtests: Subtests fixture for reporting nested test results.
    """
    # All validations use LocalRunner - they run commands on the local host
    # (even Kubernetes validations just run kubectl commands from outside the cluster)
    runner = LocalRunner()

    # Instantiate the validation (inventory is included in validation_config)
    validation = validation_class(runner=runner, config=validation_config)
    # Override name to match the configuration key (e.g. for variants like ValidationName-Variant)
    validation.name = validation_name

    # Inject subtests fixture for nested test reporting
    validation._subtests = subtests

    # Run the validation
    result = validation.execute()

    # Store result in memory for isvctl to retrieve after pytest completes
    # Get category from validation_config (set by run_validations_via_pytest)
    category = validation_config.get("_category", "")
    _validation_results.append(
        {
            "name": validation_name,
            "passed": result["passed"],
            "message": result["output"] if result["passed"] else result["error"],
            "category": category,
        }
    )

    # Assert success
    assert result["passed"], f"Validation failed: {result['error']}\nOutput: {result['output']}"
