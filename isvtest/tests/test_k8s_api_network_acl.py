# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Unit tests for ``isvtest.validations.k8s_api_network_acl``."""

from __future__ import annotations

from typing import Any

from isvtest.core.runners import CommandResult
from isvtest.utils.checks import truncate
from isvtest.validations.k8s_api_network_acl import K8sApiNetworkAclCheck


def _ok(stdout: str = "", stderr: str = "") -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr=stderr, duration=0.0)


def _fail(stdout: str = "", stderr: str = "", exit_code: int = 1) -> CommandResult:
    return CommandResult(exit_code=exit_code, stdout=stdout, stderr=stderr, duration=0.0)


def _minimal_config(**overrides: Any) -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "cluster_name": "isv-cluster",
        "authorized_probe_cmd": "kubectl get --raw /healthz",
        "unauthorized_probe_cmd": "ssh ext-host curl --max-time 5 https://api:6443/healthz",
    }
    cfg.update(overrides)
    return cfg


def _classify(cmd: str) -> str:
    if "get cluster" in cmd:
        return "cluster_read"
    if cmd.startswith("kubectl get --raw"):
        return "authorized"
    if cmd.startswith("ssh ext-host"):
        return "unauthorized"
    return "unknown"


class TestInputValidation:
    def test_missing_cluster_name_fails(self) -> None:
        check = K8sApiNetworkAclCheck(
            config={
                "authorized_probe_cmd": "a",
                "unauthorized_probe_cmd": "u",
            }
        )
        check.run()
        assert not check.passed
        assert "`cluster_name` is required" in check.message

    def test_missing_authorized_probe_cmd_fails(self) -> None:
        check = K8sApiNetworkAclCheck(
            config={
                "cluster_name": "c",
                "unauthorized_probe_cmd": "u",
            }
        )
        check.run()
        assert not check.passed
        assert "`authorized_probe_cmd` is required" in check.message

    def test_missing_unauthorized_probe_cmd_fails(self) -> None:
        check = K8sApiNetworkAclCheck(
            config={
                "cluster_name": "c",
                "authorized_probe_cmd": "a",
            }
        )
        check.run()
        assert not check.passed
        assert "`unauthorized_probe_cmd` is required" in check.message

    def test_non_integer_probe_timeout_rejected(self) -> None:
        check = K8sApiNetworkAclCheck(config=_minimal_config(probe_timeout="ten"))
        check.run()
        assert not check.passed
        assert "`probe_timeout` must be an integer" in check.message

    def test_bool_probe_timeout_rejected(self) -> None:
        check = K8sApiNetworkAclCheck(config=_minimal_config(probe_timeout=True))
        check.run()
        assert not check.passed
        assert "must be an integer, got bool" in check.message

    def test_non_bool_require_endpoint_info_rejected(self) -> None:
        check = K8sApiNetworkAclCheck(config=_minimal_config(require_endpoint_info="yes"))
        check.run()
        assert not check.passed
        assert "`require_endpoint_info` must be a boolean" in check.message


class TestEndpointRead:
    def test_cluster_read_failure_fails_when_required(self) -> None:
        check = K8sApiNetworkAclCheck(config=_minimal_config())

        def fake(cmd: str, *a: Any, **kw: Any) -> CommandResult:
            if _classify(cmd) == "cluster_read":
                return _fail(stderr='clusters.cluster.x-k8s.io "isv-cluster" not found')
            raise AssertionError(f"unexpected {cmd}")

        check.run_command = fake  # type: ignore[assignment]
        check.run()
        assert not check.passed
        assert "Unable to read Cluster" in check.message
        assert "not found" in check.message

    def test_empty_endpoint_rejected(self) -> None:
        """A resource with no ``controlPlaneEndpoint`` renders as ``:`` under
        the jsonpath format string — the check must refuse rather than
        treating it as a valid host:port."""
        check = K8sApiNetworkAclCheck(config=_minimal_config())

        def fake(cmd: str, *a: Any, **kw: Any) -> CommandResult:
            if _classify(cmd) == "cluster_read":
                return _ok(stdout=":")
            raise AssertionError(f"unexpected {cmd}")

        check.run_command = fake  # type: ignore[assignment]
        check.run()
        assert not check.passed
        assert "no `spec.controlPlaneEndpoint`" in check.message

    def test_cluster_read_skipped_when_require_endpoint_info_false(self) -> None:
        """When the operator opts out, the cluster-read is skipped entirely
        so probes are the only source of truth — needed for non-CAPI
        providers where the Cluster CRD doesn't exist."""
        check = K8sApiNetworkAclCheck(config=_minimal_config(require_endpoint_info=False))
        observed: list[str] = []

        def fake(cmd: str, *a: Any, **kw: Any) -> CommandResult:
            observed.append(_classify(cmd))
            kind = _classify(cmd)
            if kind == "authorized":
                return _ok(stdout="ok")
            if kind == "unauthorized":
                return _fail(stderr="connection timed out")
            raise AssertionError(f"unexpected {cmd}")

        check.run_command = fake  # type: ignore[assignment]
        check.run()
        assert check.passed, check.message
        assert "cluster_read" not in observed, observed

    def test_endpoint_surfaced_in_passed_message(self) -> None:
        check = K8sApiNetworkAclCheck(config=_minimal_config())

        def fake(cmd: str, *a: Any, **kw: Any) -> CommandResult:
            kind = _classify(cmd)
            if kind == "cluster_read":
                return _ok(stdout="10.0.0.42:6443")
            if kind == "authorized":
                return _ok(stdout="ok")
            if kind == "unauthorized":
                return _fail(stderr="connection timed out")
            raise AssertionError(f"unexpected {cmd}")

        check.run_command = fake  # type: ignore[assignment]
        check.run()
        assert check.passed, check.message
        assert "10.0.0.42:6443" in check.message


class TestAuthorizedProbe:
    def test_authorized_failure_aborts_with_baseline_message(self) -> None:
        """A failing authorized probe means the API is unreachable even from
        an allow-listed source. We can't then assert anything about ACLs —
        a failing unauthorized probe could equally mean 'ACL works' or
        'API dead'. The check must refuse to guess."""
        check = K8sApiNetworkAclCheck(config=_minimal_config())
        calls: list[str] = []

        def fake(cmd: str, *a: Any, **kw: Any) -> CommandResult:
            calls.append(cmd)
            kind = _classify(cmd)
            if kind == "cluster_read":
                return _ok(stdout="api.example.com:6443")
            if kind == "authorized":
                return _fail(stderr="Unable to connect to the server")
            raise AssertionError(f"unexpected {cmd}")

        check.run_command = fake  # type: ignore[assignment]
        check.run()
        assert not check.passed
        assert "Authorized probe failed" in check.message
        assert "could" in check.message and "mean" in check.message
        # Unauthorized probe must NOT have been executed.
        assert not any(_classify(c) == "unauthorized" for c in calls)

    def test_authorized_probe_runs_before_unauthorized(self) -> None:
        """Ordering matters: the baseline check must run before the
        unauthorized probe, otherwise a slow/long-timeout unauthorized
        probe wastes time on a check that was already doomed."""
        check = K8sApiNetworkAclCheck(config=_minimal_config())
        order: list[str] = []

        def fake(cmd: str, *a: Any, **kw: Any) -> CommandResult:
            kind = _classify(cmd)
            if kind == "cluster_read":
                return _ok(stdout="api.example.com:6443")
            if kind == "authorized":
                order.append("auth")
                return _ok(stdout="ok")
            if kind == "unauthorized":
                order.append("unauth")
                return _fail(stderr="timed out")
            raise AssertionError(f"unexpected {cmd}")

        check.run_command = fake  # type: ignore[assignment]
        check.run()
        assert check.passed, check.message
        assert order == ["auth", "unauth"]


class TestUnauthorizedProbe:
    def test_passes_when_unauthorized_probe_fails(self) -> None:
        check = K8sApiNetworkAclCheck(config=_minimal_config())

        def fake(cmd: str, *a: Any, **kw: Any) -> CommandResult:
            kind = _classify(cmd)
            if kind == "cluster_read":
                return _ok(stdout="api.example.com:6443")
            if kind == "authorized":
                return _ok(stdout="ok")
            if kind == "unauthorized":
                return _fail(stderr="connection refused", exit_code=7)
            raise AssertionError(f"unexpected {cmd}")

        check.run_command = fake  # type: ignore[assignment]
        check.run()
        assert check.passed, check.message
        assert "network ACL verified" in check.message
        assert "exit=7" in check.message

    def test_passes_when_unauthorized_probe_times_out(self) -> None:
        """A timeout surfaces as a non-zero exit from the runner — that must
        count as a valid 'blocked' outcome identical to connection refused."""
        check = K8sApiNetworkAclCheck(config=_minimal_config())

        def fake(cmd: str, *a: Any, **kw: Any) -> CommandResult:
            kind = _classify(cmd)
            if kind == "cluster_read":
                return _ok(stdout="api.example.com:6443")
            if kind == "authorized":
                return _ok(stdout="ok")
            if kind == "unauthorized":
                # GNU timeout exit code is 124.
                return _fail(stderr="", exit_code=124)
            raise AssertionError(f"unexpected {cmd}")

        check.run_command = fake  # type: ignore[assignment]
        check.run()
        assert check.passed, check.message

    def test_fails_when_unauthorized_probe_succeeds(self) -> None:
        """Success from the unauthorized source = no ACL in place. The
        failure message must name the endpoint so the operator knows
        *which* endpoint is exposed."""
        check = K8sApiNetworkAclCheck(config=_minimal_config())

        def fake(cmd: str, *a: Any, **kw: Any) -> CommandResult:
            kind = _classify(cmd)
            if kind == "cluster_read":
                return _ok(stdout="api.example.com:6443")
            if kind == "authorized":
                return _ok(stdout="ok")
            if kind == "unauthorized":
                return _ok(stdout='{"healthy": true}')
            raise AssertionError(f"unexpected {cmd}")

        check.run_command = fake  # type: ignore[assignment]
        check.run()
        assert not check.passed
        assert "Unauthorized probe unexpectedly succeeded" in check.message
        assert "api.example.com:6443" in check.message
        assert "no network ACL is in place" in check.message

    def test_fails_when_unauthorized_probe_command_not_found(self) -> None:
        """Exit 127 (command not found) must not be mistaken for an enforced ACL —
        a broken probe would otherwise produce a false pass."""
        check = K8sApiNetworkAclCheck(config=_minimal_config())

        def fake(cmd: str, *a: Any, **kw: Any) -> CommandResult:
            kind = _classify(cmd)
            if kind == "cluster_read":
                return _ok(stdout="api.example.com:6443")
            if kind == "authorized":
                return _ok(stdout="ok")
            if kind == "unauthorized":
                return _fail(stderr="ssh: command not found", exit_code=127)
            raise AssertionError(f"unexpected {cmd}")

        check.run_command = fake  # type: ignore[assignment]
        check.run()
        assert not check.passed
        assert "could not execute" in check.message
        assert "ssh: command not found" in check.message

    def test_fails_when_unauthorized_probe_not_executable(self) -> None:
        """Exit 126 (found but not executable) must fail loudly too."""
        check = K8sApiNetworkAclCheck(config=_minimal_config())

        def fake(cmd: str, *a: Any, **kw: Any) -> CommandResult:
            kind = _classify(cmd)
            if kind == "cluster_read":
                return _ok(stdout="api.example.com:6443")
            if kind == "authorized":
                return _ok(stdout="ok")
            if kind == "unauthorized":
                return _fail(stderr="permission denied", exit_code=126)
            raise AssertionError(f"unexpected {cmd}")

        check.run_command = fake  # type: ignore[assignment]
        check.run()
        assert not check.passed
        assert "could not execute" in check.message

    def test_probe_timeout_forwarded_to_run_command(self) -> None:
        """The configured ``probe_timeout`` must reach the runner so a
        hung unauthorized probe cannot freeze the check indefinitely."""
        check = K8sApiNetworkAclCheck(config=_minimal_config(probe_timeout=3))
        seen_timeouts: dict[str, int] = {}

        def fake(cmd: str, *a: Any, **kw: Any) -> CommandResult:
            timeout = kw.get("timeout") if "timeout" in kw else (a[0] if a else None)
            if timeout is not None:
                seen_timeouts[_classify(cmd)] = timeout
            kind = _classify(cmd)
            if kind == "cluster_read":
                return _ok(stdout="api.example.com:6443")
            if kind == "authorized":
                return _ok(stdout="ok")
            if kind == "unauthorized":
                return _fail(stderr="timed out", exit_code=124)
            raise AssertionError(f"unexpected {cmd}")

        check.run_command = fake  # type: ignore[assignment]
        check.run()
        assert check.passed, check.message
        assert seen_timeouts.get("authorized") == 3
        assert seen_timeouts.get("unauthorized") == 3


class TestTruncate:
    def test_short_text_returned_unchanged(self) -> None:
        assert truncate("short") == "short"

    def test_long_text_ellipsized_at_limit(self) -> None:
        long = "a" * 120
        out = truncate(long, limit=80)
        assert len(out) == 80
        assert out.endswith("...")
