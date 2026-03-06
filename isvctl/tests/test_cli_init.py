# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Tests for CLI initialization module."""

import logging
from unittest.mock import patch

from isvctl.cli import setup_logging


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_verbose_sets_debug_level(self) -> None:
        """Test that verbose=True sets DEBUG level."""
        with patch("logging.basicConfig") as mock_basic_config:
            setup_logging(verbose=True)
            mock_basic_config.assert_called_once()
            call_kwargs = mock_basic_config.call_args[1]
            assert call_kwargs["level"] == logging.DEBUG

    def test_non_verbose_sets_info_level(self) -> None:
        """Test that verbose=False sets INFO level."""
        with patch("logging.basicConfig") as mock_basic_config:
            setup_logging(verbose=False)
            mock_basic_config.assert_called_once()
            call_kwargs = mock_basic_config.call_args[1]
            assert call_kwargs["level"] == logging.INFO

    def test_format_includes_required_fields(self) -> None:
        """Test that log format includes timestamp, level, and message."""
        with patch("logging.basicConfig") as mock_basic_config:
            setup_logging(verbose=False)
            call_kwargs = mock_basic_config.call_args[1]
            fmt = call_kwargs["format"]
            assert "%(asctime)s" in fmt
            assert "%(levelname)s" in fmt
            assert "%(name)s" in fmt
            assert "%(message)s" in fmt

    def test_datefmt_is_configured(self) -> None:
        """Test that date format is configured."""
        with patch("logging.basicConfig") as mock_basic_config:
            setup_logging(verbose=False)
            call_kwargs = mock_basic_config.call_args[1]
            assert "datefmt" in call_kwargs
            assert call_kwargs["datefmt"] == "%Y-%m-%d %H:%M:%S"
