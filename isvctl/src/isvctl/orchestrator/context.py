# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Context management for isvctl orchestration.

The Context class manages variables used for Jinja2 templating throughout
the test lifecycle. It starts with user-provided context values and gets
enriched with inventory data from command outputs.
"""

import copy
import json
import logging
import os
import re
from datetime import UTC, datetime
from typing import Any

from isvtest.config.loader import _ternary
from jinja2 import ChainableUndefined, Environment

from isvctl.config.schema import CommandOutput, RunConfig
from isvctl.redaction import filter_env

logger = logging.getLogger(__name__)


def _create_jinja_env() -> Environment:
    """Create Jinja2 environment with custom filters.

    Uses ChainableUndefined so that chained attribute access on missing
    step outputs (e.g., ``steps.setup.kubernetes.node_count | default(4)``)
    returns Undefined instead of raising UndefinedError.  This lets the
    ``| default()`` filter work even when a step has not yet run or failed.

    Returns:
        Configured Jinja2 Environment
    """
    env = Environment(undefined=ChainableUndefined)
    env.filters["tojson"] = lambda x: json.dumps(x)
    env.filters["ternary"] = _ternary
    return env


class Context:
    """Manages context variables for Jinja2 templating.

    The context provides variables for templating in:
    - Command arguments (e.g., --nodes {{context.node_count}})
    - Test configurations (e.g., count: {{inventory.kubernetes.node_count}})

    Context is built in layers:
    1. Base context from config (context: section in YAML)
    2. Lab metadata (lab: section)
    3. Built-in variables (timestamp, etc.)
    4. Inventory from create command output

    Attributes:
        data: The full context dictionary available for templating
    """

    def __init__(self, config: RunConfig) -> None:
        """Initialize context from configuration.

        Args:
            config: The merged RunConfig
        """
        self._config = config
        self.data: dict[str, Any] = {}

        # Layer 1: User-provided context
        if config.context:
            self.data["context"] = copy.deepcopy(config.context)

        # Layer 2: Lab metadata
        if config.lab:
            self.data["lab"] = config.lab.model_dump(exclude_none=True)

        # Layer 3: Built-in variables
        now = datetime.now(UTC)
        self.data["builtin"] = {
            "timestamp": now.strftime("%Y%m%d%H%M%S"),
            "date": now.strftime("%Y-%m-%d"),
        }

        # Layer 4: Inventory (populated after create command)
        self.data["inventory"] = {}

        # Layer 5: Step outputs (populated by StepExecutor)
        self.data["steps"] = {}

        # Step phases (for inferring validation phase from step)
        self._step_phases: dict[str, str] = {}

        # Track which missing steps have already been warned about
        self._warned_missing_steps: set[str] = set()
        self._context_warnings: list[str] = []

        # Phases that were actually requested (set by orchestrator)
        self._requested_phases: set[str] | None = None

        # Phase currently being rendered (set before each per-phase render).
        # Used to suppress warnings for steps whose phase hasn't had a chance
        # to run yet (i.e., their phase comes after the current phase).
        self._current_phase: str | None = None
        self._phase_order: list[str] = []

        # Validation class names whose templates should not emit "missing step"
        # warnings. Populated with classes that pytest will deselect anyway
        # (e.g. because their marker is in exclude.markers). render_dict enters
        # a suppression zone when it recurses into a key matching one of these
        # (exact or variant form "ClassName-*"). See set_silenced_validation_names.
        self._silenced_validation_names: set[str] = set()
        self._warning_suppression_depth: int = 0

        # Layer 6: Environment variables (for {{env.VAR}} access)
        # Must be loaded before settings so settings can reference env vars.
        # Sensitive variables (API keys, secrets) are excluded to prevent
        # accidental exposure in logs, dumps, or error messages.
        self.data["env"] = filter_env(dict(os.environ))

        # Layer 7: Test settings (from tests.settings)
        # These are available as top-level variables for templating
        # Settings that contain templates are rendered after loading
        if config.tests and config.tests.settings:
            env = _create_jinja_env()
            for key, value in config.tests.settings.items():
                if isinstance(value, str) and "{{" in value and "}}" in value:
                    try:
                        template = env.from_string(value)
                        self.data[key] = template.render(**self.data)
                    except Exception:
                        # If rendering fails, store as-is (may be rendered later)
                        self.data[key] = value
                else:
                    self.data[key] = value

    def set_inventory(self, output: CommandOutput) -> None:
        """Set inventory from create command output.

        This is called after a successful create command to populate
        the inventory context used by test configurations.

        Args:
            output: Validated CommandOutput from create command
        """
        self.data["inventory"] = output.model_dump(exclude_none=True)

    def set_step_output(self, step_name: str, output: dict[str, Any]) -> None:
        """Store output from a step for use in subsequent steps.

        This is called by StepExecutor after each step completes to make
        the output available for Jinja2 templating in subsequent steps.

        Args:
            step_name: Unique identifier for the step
            output: JSON output from the step command

        Example:
            After setup step:
            >>> context.set_step_output("setup", {"cluster_name": "my-cluster"})

            Subsequent step can reference:
            >>> args: ["--cluster", "{{ steps.setup.cluster_name }}"]
        """
        self.data.setdefault("steps", {})[step_name] = output

    def set_requested_phases(self, phases: set[str]) -> None:
        """Record which phases were requested for this run.

        Used to suppress warnings for steps in phases that were
        intentionally skipped (e.g., ``--phase teardown``).

        Args:
            phases: Set of phase names that were requested
        """
        self._requested_phases = phases

    def set_silenced_validation_names(self, names: set[str]) -> None:
        """Declare validation classes whose template refs must not warn.

        Used by the orchestrator to point Context at classes that pytest
        will deselect (marker or test-name exclusion). When ``render_dict``
        recurses into a dict key that matches one of these names exactly
        or as a variant prefix (``"ClassName-..."``), warnings about missing
        step data are suppressed inside that subtree.

        Args:
            names: Class names to silence (e.g. ``{"K8sNodePoolCheck"}``).
        """
        self._silenced_validation_names = set(names or ())

    def _is_silenced_validation_name(self, name: str) -> bool:
        """Return True if ``name`` matches a silenced class exactly or as a variant."""
        if not isinstance(name, str) or not self._silenced_validation_names:
            return False
        if name in self._silenced_validation_names:
            return True
        for base in self._silenced_validation_names:
            if name.startswith(f"{base}-"):
                return True
        return False

    def set_current_phase(self, phase: str, phase_order: list[str] | None = None) -> None:
        """Record the phase currently being rendered.

        Used by ``_warn_missing_step_defaults`` to suppress warnings for
        steps whose phase hasn't had a chance to run yet (i.e., the step's
        phase comes after ``phase`` in ``phase_order``). Without this, a
        template in a later-phase validation (e.g. a ``test``-phase check
        referencing ``steps.describe_instance``) would falsely warn while
        validations are being rendered for an earlier phase.

        Args:
            phase: Current phase being rendered (e.g., ``'setup'``, ``'test'``).
            phase_order: Ordered list of all configured phases. If provided,
                replaces the known phase order used for ordering comparisons.
        """
        self._current_phase = phase
        if phase_order is not None:
            self._phase_order = list(phase_order)

    def set_step_phase(self, step_name: str, phase: str) -> None:
        """Record the phase a step belongs to.

        This allows validations to infer phase from step.

        Args:
            step_name: Unique identifier for the step
            phase: The phase this step belongs to (setup, test, teardown)
        """
        self._step_phases[step_name] = phase

    def get_step_phase(self, step_name: str) -> str | None:
        """Get the phase a step belongs to.

        Args:
            step_name: Name of the step

        Returns:
            Phase name, or None if step not found
        """
        return self._step_phases.get(step_name)

    def get_all_step_phases(self) -> dict[str, str]:
        """Get all step phases for passing to validation runners.

        Returns:
            Dictionary mapping step names to their phases
        """
        return dict(self._step_phases)

    def get_step_output(self, step_name: str) -> dict[str, Any]:
        """Get output from a previous step.

        Args:
            step_name: Name of the step to retrieve output for

        Returns:
            Step output dictionary, or empty dict if not found
        """
        return self.data.get("steps", {}).get(step_name, {})

    def get_command_context(self) -> dict[str, Any]:
        """Get context for command argument templating.

        Returns the full layered context (context, lab, builtin, inventory)
        for use in Jinja2 template rendering.

        Returns:
            Context dictionary for Jinja2 rendering
        """
        return self.data

    def get_test_context(self) -> dict[str, Any]:
        """Get context for test configuration templating.

        Returns:
            Context dictionary for Jinja2 rendering
        """
        return self.data

    def get_accumulated_context(self) -> dict[str, Any]:
        """Get all context including step outputs for Jinja2 templating.

        This is the full context available to step arguments:
        - context: User-provided context variables
        - lab: Lab metadata
        - builtin: Built-in variables (timestamp, date)
        - inventory: Inventory from setup command (legacy)
        - steps: Outputs from all completed steps

        Returns:
            Complete context dictionary for Jinja2 rendering
        """
        return self.data

    def get_warnings(self) -> list[str]:
        """Return any warnings about missing step data or fields."""
        return list(self._context_warnings)

    def render_string(self, template_str: str) -> str:
        """Render a Jinja2 template string with context.

        Args:
            template_str: String that may contain {{ }} templates

        Returns:
            Rendered string
        """
        if "{{" not in template_str or "}}" not in template_str:
            return template_str

        self._warn_missing_step_defaults(template_str)

        env = _create_jinja_env()
        template = env.from_string(template_str)
        return template.render(**self.data)

    _STEP_PATH_RE = re.compile(r"steps\.([\w.]+)")

    def _warn_missing_step_defaults(self, template_str: str) -> None:
        """Warn when a template references missing step data.

        Detects two cases that ``ChainableUndefined`` would silently absorb:

        1. **Step not run** - ``steps.setup`` is empty because ``--phase test``
           skipped setup.
        2. **Field not found** - ``steps.setup`` has output but the referenced
           field doesn't exist (typo, rename, wrong variable).

        Emits a one-time warning per unique path so operators know defaults
        are in effect and can verify they're correct.

        Args:
            template_str: Jinja2 template string to scan for step references
        """
        # Suppress everything while rendering a subtree that belongs to a
        # validation class pytest will deselect anyway (see
        # set_silenced_validation_names). Dead templates inside a never-running
        # check should not warn.
        if self._warning_suppression_depth > 0:
            return
        steps_data = self.data.get("steps", {})
        for match in self._STEP_PATH_RE.finditer(template_str):
            full_path = match.group(1)
            parts = full_path.split(".")
            step_name = parts[0]
            warn_key = f"steps.{full_path}"

            if warn_key in self._warned_missing_steps:
                continue

            if step_name not in steps_data or not steps_data[step_name]:
                # Suppress warning if the step's phase wasn't requested
                step_phase = self._step_phases.get(step_name)
                if self._requested_phases and step_phase and step_phase not in self._requested_phases:
                    continue
                # Suppress warning if the step's phase hasn't had a chance to
                # run yet (i.e., it comes after the phase currently being
                # rendered). Without this, rendering validations for an early
                # phase falsely warns about every step referenced by later
                # phases' validations.
                if step_phase and self._current_phase and self._phase_order:
                    try:
                        step_idx = self._phase_order.index(step_phase)
                        curr_idx = self._phase_order.index(self._current_phase)
                    except ValueError:
                        step_idx = curr_idx = -1
                    if step_idx > curr_idx >= 0:
                        continue
                self._warned_missing_steps.add(warn_key)
                msg = f"step '{step_name}' has no output (not run?), using defaults for: steps.{full_path}"
                logger.warning(msg)
                self._context_warnings.append(msg)
                continue

            # Step has output - walk the path to check for missing fields
            node = steps_data
            for i, part in enumerate(parts):
                if isinstance(node, dict) and part in node:
                    node = node[part]
                elif isinstance(node, dict):
                    missing = parts[i]
                    available = ", ".join(sorted(node.keys())) if node else "(empty)"
                    self._warned_missing_steps.add(warn_key)
                    msg = f"'{missing}' not found in steps.{'.'.join(parts[:i])} (available: {available})"
                    logger.warning(msg)
                    self._context_warnings.append(msg)
                    break
                else:
                    self._warned_missing_steps.add(warn_key)
                    msg = (
                        f"cannot descend into steps.{'.'.join(parts[:i])} "
                        f"(found {type(node).__name__}), using defaults for: steps.{full_path}"
                    )
                    logger.warning(msg)
                    self._context_warnings.append(msg)
                    break

    def render_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Recursively render all string values in a dictionary.

        When a key matches a silenced validation name (see
        ``set_silenced_validation_names``), the entire subtree under that key
        is rendered with missing-step warnings suppressed. That subtree's
        templates point at a check pytest will deselect, so the refs are
        effectively dead code and warnings would be noise.

        Args:
            data: Dictionary with potential template strings

        Returns:
            New dictionary with all templates rendered
        """
        result = {}
        for key, value in data.items():
            silence = self._is_silenced_validation_name(key)
            if silence:
                self._warning_suppression_depth += 1
            try:
                if isinstance(value, str):
                    result[key] = self.render_string(value)
                elif isinstance(value, dict):
                    result[key] = self.render_dict(value)
                elif isinstance(value, list):
                    result[key] = self._render_list(value)
                else:
                    result[key] = value
            finally:
                if silence:
                    self._warning_suppression_depth -= 1
        return result

    def _render_list(self, items: list[Any]) -> list[Any]:
        """Recursively render all string values in a list.

        Args:
            items: List with potential template strings

        Returns:
            New list with all templates rendered
        """
        result = []
        for item in items:
            if isinstance(item, str):
                result.append(self.render_string(item))
            elif isinstance(item, dict):
                result.append(self.render_dict(item))
            elif isinstance(item, list):
                result.append(self._render_list(item))
            else:
                result.append(item)
        return result

    def to_inventory_dict(self) -> dict[str, Any]:
        """Convert inventory to format expected by isvtest.

        Returns:
            Dictionary matching isvtest inventory schema
        """
        return self.data.get("inventory", {})
