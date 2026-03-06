# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Tests for version module."""

from importlib.metadata import PackageNotFoundError
from unittest.mock import patch

from isvreporter.version import get_version


class TestGetVersion:
    """Tests for get_version function."""

    def test_returns_metadata_version_when_installed(self) -> None:
        """When package is installed, version comes from importlib.metadata."""
        with patch("isvreporter.version.version", return_value="1.2.3") as mock:
            assert get_version("isvreporter") == "1.2.3"
            mock.assert_called_once_with("isvreporter")

    def test_returns_dev_when_package_not_found(self) -> None:
        """When metadata lookup fails, return 'dev'."""
        with patch("isvreporter.version.version", side_effect=PackageNotFoundError("nope")):
            assert get_version("nonexistent") == "dev"
