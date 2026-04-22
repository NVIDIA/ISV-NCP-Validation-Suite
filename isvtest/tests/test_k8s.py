# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Tests for Kubernetes utility functions (KUBECTL override)."""

import json
import os
from unittest.mock import patch

import pytest

from isvtest.core.k8s import (
    TERMINAL_WAITING_REASONS,
    TRANSIENT_WAITING_REASONS,
    get_k8s_provider,
    get_kubectl_base_shell,
    get_kubectl_command,
    parse_pod_state,
    parse_server_version,
)


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
        with (
            patch.dict(os.environ, {"KUBECTL": "oc"}, clear=True),
            patch("isvtest.core.k8s.shutil.which", return_value="/usr/bin/oc"),
        ):
            result = get_kubectl_command()
        assert result == ["oc"]

    def test_override_with_leading_trailing_whitespace(self) -> None:
        """KUBECTL="  oc  " strips whitespace and returns ["oc"]."""
        with (
            patch.dict(os.environ, {"KUBECTL": "  oc  "}, clear=True),
            patch("isvtest.core.k8s.shutil.which", return_value="/usr/bin/oc"),
        ):
            result = get_kubectl_command()
        assert result == ["oc"]

    def test_multi_token_prefix(self) -> None:
        """KUBECTL="microk8s kubectl" returns ["microk8s", "kubectl"]."""
        with (
            patch.dict(os.environ, {"KUBECTL": "microk8s kubectl"}, clear=True),
            patch("isvtest.core.k8s.shutil.which", return_value="/snap/bin/microk8s"),
        ):
            result = get_kubectl_command()
        assert result == ["microk8s", "kubectl"]

    def test_quoted_path_with_spaces(self) -> None:
        """KUBECTL with a quoted path containing spaces is handled by shlex."""
        with (
            patch.dict(os.environ, {"KUBECTL": '"/tmp/with space/oc"'}, clear=True),
            patch("isvtest.core.k8s.shutil.which", return_value="/tmp/with space/oc"),
        ):
            result = get_kubectl_command()
        assert result == ["/tmp/with space/oc"]

    def test_precedence_over_k8s_provider(self) -> None:
        """KUBECTL takes precedence over K8S_PROVIDER."""
        env = {"KUBECTL": "oc", "K8S_PROVIDER": "microk8s"}
        with (
            patch.dict(os.environ, env, clear=True),
            patch("isvtest.core.k8s.shutil.which", return_value="/usr/bin/oc"),
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

    def test_get_kubectl_base_shell_round_trip(self) -> None:
        """get_kubectl_base_shell() returns shell-safe string from KUBECTL override."""
        with (
            patch.dict(os.environ, {"KUBECTL": "microk8s kubectl"}, clear=True),
            patch("isvtest.core.k8s.shutil.which", return_value="/snap/bin/microk8s"),
        ):
            result = get_kubectl_base_shell()
        assert result == "microk8s kubectl"

    def test_binary_not_on_path_raises(self) -> None:
        """KUBECTL=nonexistent raises FileNotFoundError with clear message."""
        with (
            patch.dict(os.environ, {"KUBECTL": "nonexistent"}, clear=True),
            patch("isvtest.core.k8s.shutil.which", return_value=None),
        ):
            with pytest.raises(FileNotFoundError, match="not found on PATH"):
                get_kubectl_command()


class TestGetKubectlBaseShellArgs:
    """Tests for get_kubectl_base_shell() args composition."""

    def test_composes_args_with_quoting(self) -> None:
        with (
            patch.dict(os.environ, {"KUBECTL": "kubectl"}, clear=True),
            patch("isvtest.core.k8s.shutil.which", return_value="/usr/bin/kubectl"),
        ):
            result = get_kubectl_base_shell("get", "pod", "my-pod", "-n", "default")
        assert result == "kubectl get pod my-pod -n default"

    def test_quotes_arg_with_spaces(self) -> None:
        with (
            patch.dict(os.environ, {"KUBECTL": "kubectl"}, clear=True),
            patch("isvtest.core.k8s.shutil.which", return_value="/usr/bin/kubectl"),
        ):
            result = get_kubectl_base_shell("label", "node", "n1", "app=foo bar")
        # The value with a space must be quoted so the shell sees it as one token.
        assert "'app=foo bar'" in result


class TestParsePodState:
    def test_running_pod(self) -> None:
        payload = json.dumps({"status": {"phase": "Running"}})
        assert parse_pod_state(payload, "") == ("Running", "", "")

    def test_pending_with_waiting_reason(self) -> None:
        payload = json.dumps(
            {
                "status": {
                    "phase": "Pending",
                    "containerStatuses": [
                        {"state": {"waiting": {"reason": "ImagePullBackOff", "message": "back-off"}}}
                    ],
                }
            }
        )
        phase, reason, msg = parse_pod_state(payload, "")
        assert phase == "Pending"
        assert reason == "ImagePullBackOff"
        assert msg == "back-off"

    def test_notfound_from_stderr(self) -> None:
        stderr = 'Error from server (NotFound): pods "my-pod" not found'
        assert parse_pod_state("", stderr) == ("NotFound", "", "")

    def test_unknown_on_generic_failure(self) -> None:
        assert parse_pod_state("", "connection refused") == ("Unknown", "", "")

    def test_unknown_on_malformed_json(self) -> None:
        assert parse_pod_state("not json", "") == ("Unknown", "", "")

    def test_missing_container_statuses(self) -> None:
        payload = json.dumps({"status": {"phase": "Pending"}})
        assert parse_pod_state(payload, "") == ("Pending", "", "")


class TestParseServerVersion:
    def test_strips_build_metadata(self) -> None:
        assert parse_server_version(json.dumps({"serverVersion": {"gitVersion": "v1.30.2+abc"}})) == "v1.30.2"

    def test_plain_git_version(self) -> None:
        assert parse_server_version(json.dumps({"serverVersion": {"gitVersion": "v1.31.3"}})) == "v1.31.3"

    def test_missing_server_version(self) -> None:
        assert parse_server_version(json.dumps({})) is None

    def test_malformed_json(self) -> None:
        assert parse_server_version("not json") is None

    def test_unexpected_format(self) -> None:
        assert parse_server_version(json.dumps({"serverVersion": {"gitVersion": "1.x.y"}})) is None


class TestWaitingReasonConstants:
    def test_terminal_reasons_are_frozen(self) -> None:
        assert "ImagePullBackOff" in TERMINAL_WAITING_REASONS
        assert isinstance(TERMINAL_WAITING_REASONS, frozenset)

    def test_transient_reasons_are_frozen(self) -> None:
        assert "ErrImagePull" in TRANSIENT_WAITING_REASONS
        assert isinstance(TRANSIENT_WAITING_REASONS, frozenset)

    def test_terminal_and_transient_are_disjoint(self) -> None:
        assert TERMINAL_WAITING_REASONS.isdisjoint(TRANSIENT_WAITING_REASONS)
