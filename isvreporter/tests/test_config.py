"""Tests for configuration module."""

import os
from unittest.mock import MagicMock, patch

from isvreporter.config import (
    PROD_ISV_LAB_SERVICE_ENDPOINT,
    PROD_ISV_SSA_ISSUER,
    STG_ISV_LAB_SERVICE_ENDPOINT,
    STG_ISV_SSA_ISSUER,
    get_default_endpoint,
    get_default_ssa_issuer,
    is_dev_mode,
)


class TestConfigDetection:
    """Tests for environment detection."""

    def test_is_dev_mode_explicit_staging(self) -> None:
        """Test explicit staging environment via ISV_ENV."""
        with patch.dict(os.environ, {"ISV_ENV": "staging"}):
            assert is_dev_mode() is True

    def test_is_dev_mode_explicit_production(self) -> None:
        """Test explicit production environment via ISV_ENV."""
        with patch.dict(os.environ, {"ISV_ENV": "production"}):
            assert is_dev_mode() is False

    def test_is_dev_mode_case_insensitive(self) -> None:
        """Test that ISV_ENV is case-insensitive."""
        with patch.dict(os.environ, {"ISV_ENV": "STAGING"}):
            assert is_dev_mode() is True

        with patch.dict(os.environ, {"ISV_ENV": "Production"}):
            assert is_dev_mode() is False

    def test_is_dev_mode_auto_detect_from_source(self) -> None:
        """Test auto-detection returns True when running from source."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("isvreporter.config.Path") as mock_path_cls:
                # Simulate running from source (path contains src/isvreporter)
                mock_path_instance = MagicMock()
                mock_path_instance.resolve.return_value = mock_path_instance
                mock_path_instance.__str__ = lambda self: "/workspace/src/isvreporter/config.py"
                mock_path_cls.return_value = mock_path_instance
                assert is_dev_mode() is True

    def test_is_dev_mode_auto_detect_from_wheel(self) -> None:
        """Test auto-detection returns False when running from installed wheel."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("isvreporter.config.Path") as mock_path_cls:
                # Simulate running from installed wheel (site-packages)
                mock_path_instance = MagicMock()
                mock_path_instance.resolve.return_value = mock_path_instance
                mock_path_instance.__str__ = lambda self: "/usr/lib/python3.12/site-packages/isvreporter/config.py"
                mock_path_cls.return_value = mock_path_instance
                assert is_dev_mode() is False


class TestGetDefaultEndpoint:
    """Tests for get_default_endpoint function."""

    def test_returns_staging_endpoint_in_dev_mode(self) -> None:
        """Test that staging endpoint is returned in dev mode."""
        with patch.dict(os.environ, {"ISV_ENV": "staging"}):
            result = get_default_endpoint()
            assert result == STG_ISV_LAB_SERVICE_ENDPOINT

    def test_returns_prod_endpoint_in_prod_mode(self) -> None:
        """Test that production endpoint is returned in prod mode."""
        with patch.dict(os.environ, {"ISV_ENV": "production"}):
            result = get_default_endpoint()
            assert result == PROD_ISV_LAB_SERVICE_ENDPOINT


class TestGetDefaultSsaIssuer:
    """Tests for get_default_ssa_issuer function."""

    def test_returns_staging_issuer_in_dev_mode(self) -> None:
        """Test that staging issuer is returned in dev mode."""
        with patch.dict(os.environ, {"ISV_ENV": "staging"}):
            result = get_default_ssa_issuer()
            assert result == STG_ISV_SSA_ISSUER

    def test_returns_prod_issuer_in_prod_mode(self) -> None:
        """Test that production issuer is returned in prod mode."""
        with patch.dict(os.environ, {"ISV_ENV": "production"}):
            result = get_default_ssa_issuer()
            assert result == PROD_ISV_SSA_ISSUER
