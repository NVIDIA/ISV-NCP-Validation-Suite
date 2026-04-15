# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Tests for Kubernetes utility functions (KUBECTL override)."""

import os
from unittest.mock import patch

import pytest

from isvtest.core.k8s import get_k8s_provider, get_kubectl_command
from isvtest.core.ngc import get_kubectl_base


class TestGetKubectlCommandOverride:
    """Tests for KUBECTL environment variable override in get_kubectl_command()."""

    def test_unset_defaults_to_provider_detection(self) -> None:
        """Unset KUBECTL falls through to K8S_PROVIDER / auto-detection."""
        env = {"K8S_PROVIDER": "kubectl"}
        with patch.dict(os.environ, env, clear=True):
            get_k8s_provider.cache_clear()
            result = get_kubectl_command()
        assert result == ["kubectl"]

    def test_simple_override(self) -> None:
        """KUBECTL=oc returns ["oc"]."""
        with patch.dict(os.environ, {"KUBECTL": "oc"}, clear=True), patch(
            "isvtest.core.k8s.shutil.which", return_value="/usr/bin/oc"
        ):
            result = get_kubectl_command()
        assert result == ["oc"]

    def test_override_with_leading_trailing_whitespace(self) -> None:
        """KUBECTL="  oc  " strips whitespace and returns ["oc"]."""
        with patch.dict(os.environ, {"KUBECTL": "  oc  "}, clear=True), patch(
            "isvtest.core.k8s.shutil.which", return_value="/usr/bin/oc"
        ):
            result = get_kubectl_command()
        assert result == ["oc"]

    def test_multi_token_prefix(self) -> None:
        """KUBECTL="microk8s kubectl" returns ["microk8s", "kubectl"]."""
        with patch.dict(os.environ, {"KUBECTL": "microk8s kubectl"}, clear=True), patch(
            "isvtest.core.k8s.shutil.which", return_value="/snap/bin/microk8s"
        ):
            result = get_kubectl_command()
        assert result == ["microk8s", "kubectl"]

    def test_quoted_path_with_spaces(self) -> None:
        """KUBECTL with a quoted path containing spaces is handled by shlex."""
        with patch.dict(os.environ, {"KUBECTL": '"/tmp/with space/oc"'}, clear=True), patch(
            "isvtest.core.k8s.shutil.which", return_value="/tmp/with space/oc"
        ):
            result = get_kubectl_command()
        assert result == ["/tmp/with space/oc"]

    def test_precedence_over_k8s_provider(self) -> None:
        """KUBECTL takes precedence over K8S_PROVIDER."""
        env = {"KUBECTL": "oc", "K8S_PROVIDER": "microk8s"}
        with patch.dict(os.environ, env, clear=True), patch(
            "isvtest.core.k8s.shutil.which", return_value="/usr/bin/oc"
        ):
            get_k8s_provider.cache_clear()
            result = get_kubectl_command()
        assert result == ["oc"]

    def test_empty_string_falls_through(self) -> None:
        """KUBECTL="" falls through to K8S_PROVIDER detection."""
        env = {"KUBECTL": "", "K8S_PROVIDER": "kubectl"}
        with patch.dict(os.environ, env, clear=True):
            get_k8s_provider.cache_clear()
            result = get_kubectl_command()
        assert result == ["kubectl"]

    def test_whitespace_only_falls_through(self) -> None:
        """KUBECTL="   \\t  " falls through to K8S_PROVIDER detection."""
        env = {"KUBECTL": "   \t  ", "K8S_PROVIDER": "kubectl"}
        with patch.dict(os.environ, env, clear=True):
            get_k8s_provider.cache_clear()
            result = get_kubectl_command()
        assert result == ["kubectl"]

    def test_empty_quoted_value_falls_through(self) -> None:
        """KUBECTL='""' yields [""] from shlex.split; treated as invalid, falls through."""
        env = {"KUBECTL": '""', "K8S_PROVIDER": "kubectl"}
        with patch.dict(os.environ, env, clear=True):
            get_k8s_provider.cache_clear()
            result = get_kubectl_command()
        assert result == ["kubectl"]

    def test_get_kubectl_base_round_trip(self) -> None:
        """get_kubectl_base() returns shell-safe string from KUBECTL override."""
        with patch.dict(os.environ, {"KUBECTL": "microk8s kubectl"}, clear=True), patch(
            "isvtest.core.k8s.shutil.which", return_value="/snap/bin/microk8s"
        ):
            result = get_kubectl_base()
        assert result == "microk8s kubectl"

    def test_binary_not_on_path_raises(self) -> None:
        """KUBECTL=nonexistent raises FileNotFoundError with clear message."""
        with patch.dict(os.environ, {"KUBECTL": "nonexistent"}, clear=True), patch(
            "isvtest.core.k8s.shutil.which", return_value=None
        ):
            with pytest.raises(FileNotFoundError, match="not found on PATH"):
                get_kubectl_command()
