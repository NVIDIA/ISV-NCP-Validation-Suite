# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Tests for YAML merging functionality."""

from pathlib import Path
from typing import Any

import pytest

from isvctl.config.merger import apply_set_value, deep_merge, merge_yaml_files, parse_set_value


class TestDeepMerge:
    """Tests for deep_merge function."""

    def test_simple_merge(self) -> None:
        """Test merging flat dictionaries."""
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self) -> None:
        """Test merging nested dictionaries."""
        base = {"outer": {"a": 1, "b": 2}}
        override = {"outer": {"b": 3, "c": 4}}
        result = deep_merge(base, override)
        assert result == {"outer": {"a": 1, "b": 3, "c": 4}}

    def test_list_replacement(self) -> None:
        """Test that lists are replaced, not concatenated."""
        base = {"items": [1, 2, 3]}
        override = {"items": [4, 5]}
        result = deep_merge(base, override)
        assert result == {"items": [4, 5]}

    def test_original_not_modified(self) -> None:
        """Test that original dicts are not modified."""
        base = {"a": {"b": 1}}
        override = {"a": {"c": 2}}
        result = deep_merge(base, override)
        assert base == {"a": {"b": 1}}
        assert override == {"a": {"c": 2}}
        assert result == {"a": {"b": 1, "c": 2}}


class TestParseSetValue:
    """Tests for parse_set_value function."""

    def test_simple_key_value(self) -> None:
        """Test parsing simple key=value."""
        path, value = parse_set_value("key=value")
        assert path == ["key"]
        assert value == "value"

    def test_dotted_path(self) -> None:
        """Test parsing dotted key path."""
        path, value = parse_set_value("context.node_count=8")
        assert path == ["context", "node_count"]
        assert value == 8

    def test_boolean_value(self) -> None:
        """Test parsing boolean values."""
        path, value = parse_set_value("enabled=true")
        assert path == ["enabled"]
        assert value is True

    def test_list_value(self) -> None:
        """Test parsing list values."""
        path, value = parse_set_value("items=[1, 2, 3]")
        assert path == ["items"]
        assert value == [1, 2, 3]

    def test_invalid_format(self) -> None:
        """Test that invalid format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid --set format"):
            parse_set_value("no_equals_sign")

    def test_empty_key_raises(self) -> None:
        """Test that empty key raises ValueError."""
        with pytest.raises(ValueError, match="non-empty"):
            parse_set_value("=value")

    def test_yaml_error_fallback(self) -> None:
        """Test that invalid YAML falls back to string."""
        path, value = parse_set_value("key={invalid yaml")
        assert path == ["key"]
        assert value == "{invalid yaml"  # Falls back to string


class TestApplySetValue:
    """Tests for apply_set_value function."""

    def test_simple_set(self) -> None:
        """Test setting a simple value."""
        config: dict[str, Any] = {}
        apply_set_value(config, ["key"], "value")
        assert config == {"key": "value"}

    def test_nested_set(self) -> None:
        """Test setting a nested value."""
        config: dict[str, Any] = {}
        apply_set_value(config, ["context", "node_count"], 8)
        assert config == {"context": {"node_count": 8}}

    def test_override_existing(self) -> None:
        """Test overriding an existing value."""
        config = {"context": {"node_count": 4, "other": "keep"}}
        apply_set_value(config, ["context", "node_count"], 8)
        assert config == {"context": {"node_count": 8, "other": "keep"}}

    def test_overwrite_non_dict_with_dict(self) -> None:
        """Test overwriting a non-dict value when creating nested path."""
        config: dict[str, Any] = {"context": "string"}  # Not a dict
        apply_set_value(config, ["context", "node_count"], 8)
        assert config == {"context": {"node_count": 8}}  # Overwrites string with dict


class TestMergeYamlFiles:
    """Tests for merge_yaml_files function."""

    def test_merge_single_file(self, tmp_path: Path) -> None:
        """Test merging a single YAML file."""
        file1 = tmp_path / "config.yaml"
        file1.write_text("a: 1\nb: 2")

        result = merge_yaml_files([str(file1)])
        assert result == {"a": 1, "b": 2}

    def test_merge_multiple_files(self, tmp_path: Path) -> None:
        """Test merging multiple YAML files."""
        file1 = tmp_path / "base.yaml"
        file1.write_text("a: 1\nb: 2")
        file2 = tmp_path / "override.yaml"
        file2.write_text("b: 3\nc: 4")

        result = merge_yaml_files([str(file1), str(file2)])
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_merge_with_set_values(self, tmp_path: Path) -> None:
        """Test --set overrides."""
        file1 = tmp_path / "config.yaml"
        file1.write_text("node_count: 4\nother: keep")

        result = merge_yaml_files([str(file1)], set_values=["node_count=8"])
        assert result == {"node_count": 8, "other": "keep"}

    def test_merge_with_nested_set_values(self, tmp_path: Path) -> None:
        """Test --set with nested paths."""
        file1 = tmp_path / "config.yaml"
        file1.write_text("context:\n  node_count: 4")

        result = merge_yaml_files([str(file1)], set_values=["context.node_count=8"])
        assert result == {"context": {"node_count": 8}}

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        """Test that missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="not found"):
            merge_yaml_files([str(tmp_path / "nonexistent.yaml")])

    def test_non_dict_yaml_raises(self, tmp_path: Path) -> None:
        """Test that non-dict YAML raises ValueError."""
        file1 = tmp_path / "invalid.yaml"
        file1.write_text("- item1\n- item2")  # List, not dict

        with pytest.raises(ValueError, match="must contain a YAML mapping"):
            merge_yaml_files([str(file1)])

    def test_empty_file_ignored(self, tmp_path: Path) -> None:
        """Test that empty YAML files are ignored."""
        file1 = tmp_path / "empty.yaml"
        file1.write_text("")
        file2 = tmp_path / "valid.yaml"
        file2.write_text("a: 1")

        result = merge_yaml_files([str(file1), str(file2)])
        assert result == {"a": 1}
