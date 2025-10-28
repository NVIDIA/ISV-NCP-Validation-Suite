"""YAML configuration merging utilities.

This module provides deep-merge functionality for combining multiple YAML
configuration files, similar to Helm's --values flag behavior.

Later files override earlier ones. The --set flag can override individual values.
"""

import copy
from pathlib import Path
from typing import Any

import yaml


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dictionaries.

    Values from `override` take precedence. Nested dicts are merged recursively.
    Lists are replaced entirely (not concatenated).

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
