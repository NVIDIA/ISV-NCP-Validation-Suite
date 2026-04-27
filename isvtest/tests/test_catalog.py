# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Tests for the catalog module."""

from unittest.mock import patch

from isvtest.catalog import build_catalog, get_catalog_version


class TestBuildCatalog:
    """Tests for build_catalog function."""

    def test_returns_list_of_dicts(self) -> None:
        """Test that build_catalog returns a list of dicts."""
        catalog = build_catalog()
        assert isinstance(catalog, list)
        assert len(catalog) > 0
        for entry in catalog:
            assert isinstance(entry, dict)

    def test_entries_have_required_keys(self) -> None:
        """Test that each entry has the required keys."""
        catalog = build_catalog()
        for entry in catalog:
            assert "name" in entry
            assert "description" in entry
            assert "markers" in entry
            assert "module" in entry

    def test_entries_have_correct_types(self) -> None:
        """Test that entry values have the correct types."""
        catalog = build_catalog()
        for entry in catalog:
            assert isinstance(entry["name"], str)
            assert isinstance(entry["description"], str)
            assert isinstance(entry["markers"], list)
            assert isinstance(entry["module"], str)

    def test_no_duplicate_names(self) -> None:
        """Test that there are no duplicate test names in the catalog."""
        catalog = build_catalog()
        names = [e["name"] for e in catalog]
        assert len(names) == len(set(names))

    def test_known_tests_present(self) -> None:
        """Test that some known validation tests appear in the catalog."""
        catalog = build_catalog()
        names = {e["name"] for e in catalog}
        assert "StepSuccessCheck" in names
        assert "FieldExistsCheck" in names

    def test_markers_are_lists_of_strings(self) -> None:
        """Test that markers are lists of strings."""
        catalog = build_catalog()
        for entry in catalog:
            for marker in entry["markers"]:
                assert isinstance(marker, str)

    def test_modules_are_valid_python_paths(self) -> None:
        """Test that module paths look like valid Python module paths."""
        catalog = build_catalog()
        for entry in catalog:
            assert "." in entry["module"]
            assert entry["module"].startswith("isvtest.")

    def test_platforms_come_from_suites_before_filter_markers(self) -> None:
        """Test that feature markers do not add extra platform ownership."""
        catalog = build_catalog()
        by_name = {entry["name"]: entry for entry in catalog}

        assert by_name["SgCrudCheck"]["platforms"] == ["NETWORK"]
        assert by_name["BmcTenantIsolationCheck"]["platforms"] == ["SECURITY"]
        assert by_name["ServiceAccountCredentialCheck"]["platforms"] == ["SECURITY"]
        assert by_name["ConsoleRbacCheck"]["platforms"] == ["VM"]
        assert by_name["OidcUserAuthCheck"]["platforms"] == ["SECURITY"]


class TestGetCatalogVersion:
    """Tests for get_catalog_version function."""

    def test_returns_string(self) -> None:
        """Test that get_catalog_version returns a string."""
        version = get_catalog_version()
        assert isinstance(version, str)
        assert len(version) > 0

    def test_returns_dev_when_not_installed(self) -> None:
        """Test that 'dev' is returned when package is not installed."""
        from importlib.metadata import PackageNotFoundError

        with patch(
            "isvreporter.version.version",
            side_effect=PackageNotFoundError("isvtest"),
        ):
            version = get_catalog_version()
            assert version == "dev"
