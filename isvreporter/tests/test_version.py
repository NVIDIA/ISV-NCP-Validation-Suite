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
