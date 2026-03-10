# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Tests for YAML merging functionality."""

import copy
from pathlib import Path
from typing import Any

import pytest

from isvctl.config.merger import (
    _has_merge_marker,
    _is_mergeable_list,
    _merge_single_key_dict_lists,
    _strip_merge_marker,
    apply_set_value,
    deep_merge,
    merge_yaml_files,
    parse_set_value,
)


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

    def test_remove_string_is_literal_at_dict_level(self) -> None:
        """__remove__ at dict level is treated as a literal string value."""
        base = {"a": 1, "b": 2, "c": 3}
        override = {"b": "__remove__"}
        result = deep_merge(base, override)
        # __remove__ only works inside strategic-merge lists, not at dict level
        assert result == {"a": 1, "b": "__remove__", "c": 3}

    def test_remove_only_in_strategic_merge_lists(self) -> None:
        """__remove__ deletes items only within strategic-merge lists."""
        base = {"checks": [{"A": {"p": 1}}, {"B": {"p": 2}}]}
        override = {"checks": [{"__merge__": True}, {"B": "__remove__"}]}
        result = deep_merge(base, override)
        # B is removed from the list, A is kept
        assert result == {"checks": [{"A": {"p": 1}}]}

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


class TestStrategicMerge:
    """Tests for opt-in strategic merge of single-key dict lists.

    Strategic merge is triggered by including ``{__merge__: true}`` in the
    override list.  Without the marker, lists are replaced as before.
    """

    # -- marker helpers -------------------------------------------------------

    def test_has_merge_marker(self) -> None:
        """_has_merge_marker detects the opt-in marker."""
        assert _has_merge_marker([{"__merge__": True}]) is True
        assert _has_merge_marker([{"__merge__": True}, {"A": 1}]) is True
        assert _has_merge_marker([{"A": 1}]) is False
        assert _has_merge_marker([]) is False

    def test_strip_merge_marker(self) -> None:
        """_strip_merge_marker removes only the marker item."""
        lst = [{"__merge__": True}, {"A": 1}, {"B": 2}]
        assert _strip_merge_marker(lst) == [{"A": 1}, {"B": 2}]

    def test_is_mergeable_list_helper(self) -> None:
        """Direct tests for _is_mergeable_list."""
        assert _is_mergeable_list([{"A": 1}]) is True
        assert _is_mergeable_list([{"A": 1}, {"B": 2}]) is True
        assert _is_mergeable_list([]) is False
        assert _is_mergeable_list([1, 2]) is False
        assert _is_mergeable_list(["a", "b"]) is False
        assert _is_mergeable_list([{"A": 1, "B": 2}]) is False
        assert _is_mergeable_list([{"A": 1}, "b"]) is False

    # -- opt-in behavior via deep_merge ---------------------------------------

    def test_no_marker_replaces_list(self) -> None:
        """Without __merge__, single-key dict lists are replaced (backward compat)."""
        base = {"checks": [{"A": {"p": 1}}, {"B": {"p": 2}}]}
        override = {"checks": [{"A": {"p": 99}}]}
        result = deep_merge(base, override)
        # B is gone — full replacement
        assert result == {"checks": [{"A": {"p": 99}}]}

    def test_merge_matching_check_params(self) -> None:
        """Core case: merge params of a matching check."""
        base = {"checks": [{"CheckA": {"param1": 1, "param2": 2}}]}
        override = {"checks": [{"__merge__": True}, {"CheckA": {"param2": 99}}]}
        result = deep_merge(base, override)
        assert result == {"checks": [{"CheckA": {"param1": 1, "param2": 99}}]}

    def test_append_new_check(self) -> None:
        """New check in override is appended to end."""
        base = {"checks": [{"CheckA": {"p": 1}}]}
        override = {"checks": [{"__merge__": True}, {"CheckB": {"p": 2}}]}
        result = deep_merge(base, override)
        assert result == {"checks": [{"CheckA": {"p": 1}}, {"CheckB": {"p": 2}}]}

    def test_remove_check_via_sentinel(self) -> None:
        """Check removed when value is '__remove__'."""
        base = {"checks": [{"CheckA": {"p": 1}}, {"CheckB": {"p": 2}}]}
        override = {"checks": [{"__merge__": True}, {"CheckA": "__remove__"}]}
        result = deep_merge(base, override)
        assert result == {"checks": [{"CheckB": {"p": 2}}]}

    def test_preserve_base_order_append_new(self) -> None:
        """Base order preserved; new items appended at end."""
        base = {"checks": [{"A": {}}, {"B": {}}, {"C": {}}]}
        override = {"checks": [{"__merge__": True}, {"D": {"new": True}}, {"B": {"updated": True}}]}
        result = deep_merge(base, override)
        assert result == {
            "checks": [
                {"A": {}},
                {"B": {"updated": True}},
                {"C": {}},
                {"D": {"new": True}},
            ]
        }

    def test_regular_lists_still_replaced(self) -> None:
        """Regular lists (scalars) use replace behavior even with no marker."""
        base = {"items": [1, 2, 3]}
        override = {"items": [4, 5]}
        result = deep_merge(base, override)
        assert result == {"items": [4, 5]}

    def test_marker_with_non_mergeable_base_strips_marker(self) -> None:
        """Marker present but base not mergeable: replace with stripped list."""
        base = {"items": [{"A": {}}, "string"]}
        override = {"items": [{"__merge__": True}, {"B": {}}]}
        result = deep_merge(base, override)
        assert result == {"items": [{"B": {}}]}

    def test_marker_with_multi_key_dicts_strips_marker(self) -> None:
        """Marker present but override items have >1 key: replace with stripped list."""
        base = {"items": [{"A": 1}]}
        override = {"items": [{"__merge__": True}, {"C": 3, "D": 4}]}
        result = deep_merge(base, override)
        assert result == {"items": [{"C": 3, "D": 4}]}

    def test_empty_base_list_with_marker(self) -> None:
        """Empty base list not mergeable; marker list replaces (stripped)."""
        base = {"items": []}
        override = {"items": [{"__merge__": True}, {"A": {}}]}
        result = deep_merge(base, override)
        assert result == {"items": [{"A": {}}]}

    def test_empty_dict_values_merge(self) -> None:
        """Checks with {} values merge correctly."""
        base = {"checks": [{"CheckA": {}}]}
        override = {"checks": [{"__merge__": True}, {"CheckA": {"new_param": True}}]}
        result = deep_merge(base, override)
        assert result == {"checks": [{"CheckA": {"new_param": True}}]}

    def test_variant_names_stay_separate(self) -> None:
        """Variant names like -1b and -3b are distinct keys."""
        base = {
            "checks": [
                {"Workload-1b": {"gpu": 1}},
                {"Workload-3b": {"gpu": 4}},
            ]
        }
        override = {"checks": [{"__merge__": True}, {"Workload-1b": {"gpu": 2}}]}
        result = deep_merge(base, override)
        assert result == {
            "checks": [
                {"Workload-1b": {"gpu": 2}},
                {"Workload-3b": {"gpu": 4}},
            ]
        }

    def test_inputs_not_mutated(self) -> None:
        """Original base and override are not modified."""
        base = {"checks": [{"A": {"p": 1}}, {"B": {"p": 2}}]}
        override = {"checks": [{"__merge__": True}, {"A": {"p": 99}}, {"C": {"p": 3}}]}
        base_copy = copy.deepcopy(base)
        override_copy = copy.deepcopy(override)
        deep_merge(base, override)
        assert base == base_copy
        assert override == override_copy

    def test_remove_nonexistent_check_is_noop(self) -> None:
        """Removing a check that doesn't exist in base is a no-op."""
        base = {"checks": [{"A": {"p": 1}}]}
        override = {"checks": [{"__merge__": True}, {"Z": "__remove__"}]}
        result = deep_merge(base, override)
        assert result == {"checks": [{"A": {"p": 1}}]}


    def test_merge_marker_requires_true(self) -> None:
        """__merge__: false should NOT trigger strategic merge."""
        base = {"checks": [{"A": {"p": 1}}, {"B": {"p": 2}}]}
        override = {"checks": [{"__merge__": False}, {"A": {"p": 99}}]}
        result = deep_merge(base, override)
        # No strategic merge — entire list is replaced (marker stripped)
        assert result == {"checks": [{"A": {"p": 99}}]}

    def test_duplicate_override_keys_deduplicated(self) -> None:
        """Duplicate new keys in override list should only appear once."""
        base = {"checks": [{"A": {"p": 1}}]}
        override = {"checks": [{"__merge__": True}, {"B": {"p": 2}}, {"B": {"p": 3}}]}
        result = deep_merge(base, override)
        # B should appear once (first occurrence wins in override_by_key)
        b_items = [item for item in result["checks"] if "B" in item]
        assert len(b_items) == 1

    def test_merge_marker_stripped_when_base_key_missing(self) -> None:
        """Merge marker should not leak into result when base key doesn't exist."""
        base = {"other": "value"}
        override = {"checks": [{"__merge__": True}, {"A": {"p": 1}}]}
        result = deep_merge(base, override)
        # Marker should be stripped, only A remains
        assert result == {"other": "value", "checks": [{"A": {"p": 1}}]}


class TestLayeredConfigs:
    """Integration tests for layered template + provider configs."""

    CONFIGS_DIR = Path(__file__).parent.parent / "configs"

    def test_template_has_no_commands(self) -> None:
        """Templates should define validations only, no commands."""
        template = merge_yaml_files([self.CONFIGS_DIR / "templates" / "kaas.yaml"])
        assert "commands" not in template, "Template should not contain commands"
        assert "tests" in template, "Template must contain tests"
        assert "validations" in template["tests"], "Template must contain validations"

    def test_layered_merge_has_both(self) -> None:
        """Template + provider merge should have both commands and tests."""
        merged = merge_yaml_files([
            self.CONFIGS_DIR / "templates" / "kaas.yaml",
            self.CONFIGS_DIR / "aws" / "eks-layered.yaml",
        ])
        assert "commands" in merged, "Merged config must have commands from provider"
        assert "tests" in merged, "Merged config must have tests from template"
        assert "kubernetes" in merged["commands"], "Commands must have kubernetes key"
        steps = merged["commands"]["kubernetes"]["steps"]
        assert any(s["name"] == "provision_cluster" for s in steps)

    def test_context_overrides_flow_through(self) -> None:
        """Provider context values should appear in the merged config."""
        merged = merge_yaml_files([
            self.CONFIGS_DIR / "templates" / "kaas.yaml",
            self.CONFIGS_DIR / "aws" / "eks-layered.yaml",
        ])
        assert merged.get("context", {}).get("total_gpus") == "1"

    def test_standalone_eks_still_works(self) -> None:
        """Self-contained eks.yaml should parse with both commands and tests."""
        standalone = merge_yaml_files([self.CONFIGS_DIR / "aws" / "eks.yaml"])
        assert "commands" in standalone
        assert "tests" in standalone
        assert "validations" in standalone["tests"]

    def test_layered_checks_match_standalone_structure(self) -> None:
        """Layered and standalone should have the same validation check names."""
        standalone = merge_yaml_files([self.CONFIGS_DIR / "aws" / "eks.yaml"])
        layered = merge_yaml_files([
            self.CONFIGS_DIR / "templates" / "kaas.yaml",
            self.CONFIGS_DIR / "aws" / "eks-layered.yaml",
        ])

        def get_check_names(config: dict[str, Any]) -> set[str]:
            names: set[str] = set()
            for group in config.get("tests", {}).get("validations", {}).values():
                for check in group:
                    if isinstance(check, dict):
                        names.update(check.keys())
            return names

        standalone_checks = get_check_names(standalone)
        layered_checks = get_check_names(layered)
        assert standalone_checks == layered_checks, (
            f"Check mismatch: standalone-only={standalone_checks - layered_checks}, "
            f"layered-only={layered_checks - standalone_checks}"
        )

    def test_all_templates_are_validation_only(self) -> None:
        """All template YAML files should have tests but no commands."""
        template_dir = self.CONFIGS_DIR / "templates"
        for yaml_file in sorted(template_dir.glob("*.yaml")):
            config = merge_yaml_files([yaml_file])
            assert "commands" not in config, f"{yaml_file.name} should not have commands"
            assert "tests" in config, f"{yaml_file.name} must have tests"
