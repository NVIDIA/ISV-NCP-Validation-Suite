# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""YAML configuration merging utilities.

This module provides deep-merge functionality for combining multiple YAML
configuration files, similar to Helm's --values flag behavior.

Later files override earlier ones. The --set flag can override individual values.
"""

import copy
import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


_MERGE_MARKER = "__merge__"


def _is_mergeable_list(lst: list[Any]) -> bool:
    """Check if a list can be strategically merged.

    Returns True if the list is non-empty and every item is a dict with exactly
    one key. This pattern matches config lists like checks where each item is
    ``{"CheckName": {params}}``.
    """
    if not lst:
        return False
    return all(isinstance(item, dict) and len(item) == 1 for item in lst)


def _has_merge_marker(lst: list[Any]) -> bool:
    """Check if a list contains the ``__merge__`` opt-in marker."""
    return any(
        isinstance(item, dict) and len(item) == 1 and _MERGE_MARKER in item
        for item in lst
    )


def _strip_merge_marker(lst: list[Any]) -> list[Any]:
    """Return a copy of the list with the ``__merge__`` marker removed."""
    return [
        item for item in lst
        if not (isinstance(item, dict) and len(item) == 1 and _MERGE_MARKER in item)
    ]


def _merge_single_key_dict_lists(
    base_list: list[dict[str, Any]], override_list: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Merge two lists of single-key dicts by matching on the dict key.

    - Matching key: deep-merge the params (override wins on conflicts)
    - New key in override: append to end
    - Key not in override: keep unchanged
    - Value set to ``"__remove__"``: delete the item

    Preserves base list order; new items from override appended at end.
    """
    # Build an index of override items keyed by their single key
    override_by_key: dict[str, Any] = {}
    override_order: list[str] = []
    for item in override_list:
        key = next(iter(item))
        override_by_key[key] = item[key]
        override_order.append(key)

    seen_keys: set[str] = set()
    result: list[dict[str, Any]] = []

    # Walk base list, merging or removing as needed
    for item in base_list:
        key = next(iter(item))
        seen_keys.add(key)

        if key in override_by_key:
            override_value = override_by_key[key]
            if override_value == "__remove__":
                continue  # Drop this item
            base_value = item[key]
            if isinstance(base_value, dict) and isinstance(override_value, dict):
                merged = deep_merge(base_value, override_value)
            else:
                merged = copy.deepcopy(override_value)
            result.append({key: merged})
        else:
            result.append(copy.deepcopy(item))

    # Append new items from override that weren't in base
    for key in override_order:
        if key not in seen_keys:
            if override_by_key[key] == "__remove__":
                continue  # Removing nonexistent key is a no-op
            result.append({key: copy.deepcopy(override_by_key[key])})

    return result


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dictionaries.

    Values from `override` take precedence. Nested dicts are merged recursively.
    Lists are replaced entirely by default. When the override list contains a
    ``{__merge__: true}`` marker and both lists are single-key dict lists, they
    are merged by matching on the dict key instead.

    Args:
        base: Base dictionary
        override: Dictionary with values to override

    Returns:
        Merged dictionary (new object, inputs not modified)
    """
    result = copy.deepcopy(base)

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            # Recursively merge nested dicts
            result[key] = deep_merge(result[key], value)
        elif (
            key in result
            and isinstance(result[key], list)
            and isinstance(value, list)
            and _has_merge_marker(value)
        ):
            # Opt-in strategic merge for lists of single-key dicts
            override_items = _strip_merge_marker(value)
            if _is_mergeable_list(result[key]) and _is_mergeable_list(override_items):
                override_keys = [next(iter(item)) for item in override_items]
                logger.debug(
                    "Strategic merge on '%s': %d base items, %d override items %s",
                    key, len(result[key]), len(override_items), override_keys,
                )
                result[key] = _merge_single_key_dict_lists(result[key], override_items)
            else:
                logger.debug(
                    "Merge marker on '%s' but lists not mergeable, replacing", key,
                )
                result[key] = copy.deepcopy(override_items)
        else:
            # Override with new value (including None)
            result[key] = copy.deepcopy(value)

    return result


def parse_set_value(set_string: str) -> tuple[list[str], Any]:
    """Parse a --set value string into path and value.

    Supports dotted paths like 'context.node_count=8'.
    Values are parsed as YAML to support types (int, bool, list, etc.).

    Args:
        set_string: String in format 'key.path=value'

    Returns:
        Tuple of (path parts, parsed value)

    Raises:
        ValueError: If string format is invalid
    """
    if "=" not in set_string:
        raise ValueError(f"Invalid --set format: '{set_string}'. Expected 'key=value' or 'key.path=value'")

    key_path, value_str = set_string.split("=", 1)
    if not key_path:
        raise ValueError(f"Invalid --set format: '{set_string}'. Expected non-empty 'key=value' or 'key.path=value'")
    path_parts = key_path.split(".")

    # Parse value as YAML to handle types
    try:
        value = yaml.safe_load(value_str)
    except yaml.YAMLError:
        # Fall back to string if YAML parsing fails
        value = value_str

    return path_parts, value


def apply_set_value(config: dict[str, Any], path_parts: list[str], value: Any) -> None:
    """Apply a single --set value to a config dict (in-place).

    Args:
        config: Configuration dictionary to modify
        path_parts: List of keys representing the path (e.g., ['context', 'node_count'])
        value: Value to set
    """
    current = config
    for part in path_parts[:-1]:
        if part not in current:
            current[part] = {}
        elif not isinstance(current[part], dict):
            # Overwrite non-dict with empty dict
            current[part] = {}
        current = current[part]

    current[path_parts[-1]] = value


def merge_yaml_files(file_paths: list[str], set_values: list[str] | None = None) -> dict[str, Any]:
    """Merge multiple YAML files with optional --set overrides.

    Files are merged in order - later files override earlier ones.
    --set values are applied after all files are merged.

    Args:
        file_paths: List of paths to YAML files
        set_values: Optional list of --set strings (e.g., ['context.node_count=8'])

    Returns:
        Merged configuration dictionary

    Raises:
        FileNotFoundError: If a file doesn't exist
        yaml.YAMLError: If YAML parsing fails
    """
    result: dict[str, Any] = {}

    for file_path in file_paths:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {file_path}")

        with open(path) as f:
            content = yaml.safe_load(f)

        if content is not None and not isinstance(content, dict):
            raise ValueError(
                f"Configuration file must contain a YAML mapping, not {type(content).__name__}: {file_path}"
            )

        if content:
            result = deep_merge(result, content)

    # Apply --set overrides
    if set_values:
        for set_string in set_values:
            path_parts, value = parse_set_value(set_string)
            apply_set_value(result, path_parts, value)

    return result
