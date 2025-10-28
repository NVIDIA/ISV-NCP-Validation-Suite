"""Tests for version module."""

import subprocess
from unittest.mock import MagicMock, patch


class TestGetVersion:
    """Tests for get_version function."""

    def test_returns_baked_version_when_available(self) -> None:
        """Test that baked _version module takes priority."""
        mock_module = MagicMock()
        mock_module.__version__ = "1.2.3"

        with patch("isvreporter.version.importlib") as mock_importlib:
            mock_importlib.import_module.return_value = mock_module
            # Import fresh to use the patched importlib
            from isvreporter.version import get_version

            result = get_version("isvreporter")
            assert result == "1.2.3"

    def test_falls_back_to_git_when_version_module_missing(self) -> None:
        """Test fallback to git SHA when _version module doesn't exist."""
        with patch("isvreporter.version.importlib") as mock_importlib:
            with patch("isvreporter.version.subprocess") as mock_subprocess:
                mock_importlib.import_module.side_effect = ModuleNotFoundError
                mock_subprocess.run.return_value = MagicMock(returncode=0, stdout="abc1234\n")
                mock_subprocess.TimeoutExpired = subprocess.TimeoutExpired

                from isvreporter.version import get_version

                result = get_version("isvreporter")
                assert result == "dev-abc1234"

    def test_falls_back_to_git_when_version_attr_missing(self) -> None:
        """Test fallback to git when __version__ attribute is missing."""
        with patch("isvreporter.version.importlib") as mock_importlib:
            with patch("isvreporter.version.subprocess") as mock_subprocess:
                mock_importlib.import_module.side_effect = AttributeError
                mock_subprocess.run.return_value = MagicMock(returncode=0, stdout="def5678\n")
                mock_subprocess.TimeoutExpired = subprocess.TimeoutExpired

                from isvreporter.version import get_version

                result = get_version("isvreporter")
                assert result == "dev-def5678"

    def test_returns_dev_local_when_git_fails(self) -> None:
        """Test fallback to dev-local when git command fails."""
        with patch("isvreporter.version.importlib") as mock_importlib:
            with patch("isvreporter.version.subprocess") as mock_subprocess:
                mock_importlib.import_module.side_effect = ModuleNotFoundError
                mock_subprocess.run.return_value = MagicMock(returncode=1, stdout="")
                mock_subprocess.TimeoutExpired = subprocess.TimeoutExpired

                from isvreporter.version import get_version

                result = get_version("isvreporter")
                assert result == "dev-local"

    def test_returns_dev_local_when_git_not_found(self) -> None:
        """Test fallback to dev-local when git is not installed."""
        with patch("isvreporter.version.importlib") as mock_importlib:
            with patch("isvreporter.version.subprocess") as mock_subprocess:
                mock_importlib.import_module.side_effect = ModuleNotFoundError
                mock_subprocess.run.side_effect = FileNotFoundError
                mock_subprocess.TimeoutExpired = subprocess.TimeoutExpired

                from isvreporter.version import get_version

                result = get_version("isvreporter")
                assert result == "dev-local"

    def test_returns_dev_local_when_git_times_out(self) -> None:
        """Test fallback to dev-local when git command times out."""
        with patch("isvreporter.version.importlib") as mock_importlib:
            with patch("isvreporter.version.subprocess") as mock_subprocess:
                mock_importlib.import_module.side_effect = ModuleNotFoundError
                mock_subprocess.run.side_effect = subprocess.TimeoutExpired("git", 5)
                mock_subprocess.TimeoutExpired = subprocess.TimeoutExpired

                from isvreporter.version import get_version

                result = get_version("isvreporter")
                assert result == "dev-local"

    def test_returns_dev_local_on_os_error(self) -> None:
        """Test fallback to dev-local on OSError."""
        with patch("isvreporter.version.importlib") as mock_importlib:
            with patch("isvreporter.version.subprocess") as mock_subprocess:
                mock_importlib.import_module.side_effect = ModuleNotFoundError
                mock_subprocess.run.side_effect = OSError("Permission denied")
                mock_subprocess.TimeoutExpired = subprocess.TimeoutExpired

                from isvreporter.version import get_version

                result = get_version("isvreporter")
                assert result == "dev-local"

    def test_git_sha_is_stripped(self) -> None:
        """Test that git SHA whitespace is stripped."""
        with patch("isvreporter.version.importlib") as mock_importlib:
            with patch("isvreporter.version.subprocess") as mock_subprocess:
                mock_importlib.import_module.side_effect = ModuleNotFoundError
                mock_subprocess.run.return_value = MagicMock(returncode=0, stdout="  abc1234  \n")
                mock_subprocess.TimeoutExpired = subprocess.TimeoutExpired

                from isvreporter.version import get_version

                result = get_version("isvreporter")
                assert result == "dev-abc1234"
