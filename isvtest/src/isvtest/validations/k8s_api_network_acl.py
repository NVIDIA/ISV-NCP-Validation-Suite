# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Verify the Kubernetes API endpoint is protected by network access controls."""

from __future__ import annotations

import shlex
from typing import Any, ClassVar

from isvtest.core.k8s import get_kubectl_base_shell
from isvtest.core.validation import BaseValidation
from isvtest.utils.checks import truncate

_DEFAULT_NAMESPACE = "default"
_DEFAULT_PROBE_TIMEOUT = 10


class K8sApiNetworkAclCheck(BaseValidation):
    """Verify a Cluster API control-plane endpoint enforces network ACLs via operator-supplied probes."""

    description: ClassVar[str] = "Verify the Kubernetes API endpoint is protected by network access controls."
    timeout: ClassVar[int] = 120
    markers: ClassVar[list[str]] = ["kubernetes"]

    def run(self) -> None:
        """Execute the endpoint read, authorized baseline probe, and unauthorized probe flow."""
        cfg = self._parse_config()
        if cfg is None:
            return

        endpoint_info: str | None = None
        if cfg["require_endpoint_info"]:
            endpoint_info = self._read_endpoint(cfg["cluster_name"], cfg["namespace"])
            if endpoint_info is None:
                return

        if not self._run_authorized_probe(cfg["authorized_probe_cmd"], cfg["probe_timeout"]):
            return

        self._run_unauthorized_probe(
            unauthorized_probe_cmd=cfg["unauthorized_probe_cmd"],
            probe_timeout=cfg["probe_timeout"],
            endpoint_info=endpoint_info,
        )

    def _parse_config(self) -> dict[str, Any] | None:
        """Validate and normalize check configuration, or ``None`` after calling ``set_failed``."""
        cluster_name = self.config.get("cluster_name")
        if not cluster_name or not isinstance(cluster_name, str):
            self.set_failed("`cluster_name` is required and must be a string (the CAPI Cluster resource name).")
            return None

        namespace = str(self.config.get("namespace", _DEFAULT_NAMESPACE))

        authorized = self.config.get("authorized_probe_cmd")
        if not authorized or not isinstance(authorized, str):
            self.set_failed(
                "`authorized_probe_cmd` is required and must be a string (a shell "
                "command expected to successfully reach the API, e.g. "
                "`kubectl --kubeconfig /path/to/kubeconfig get --raw /healthz`). "
                "Without this baseline a failing unauthorized probe cannot be "
                "distinguished from a dead cluster."
            )
            return None

        unauthorized = self.config.get("unauthorized_probe_cmd")
        if not unauthorized or not isinstance(unauthorized, str):
            self.set_failed(
                "`unauthorized_probe_cmd` is required and must be a string (a "
                "shell command expected to FAIL or time out because the source "
                "network is not allow-listed, e.g. "
                "`ssh external-host curl --max-time 5 https://<endpoint>:6443/healthz`)."
            )
            return None

        probe_timeout = self._parse_positive_int("probe_timeout", default=_DEFAULT_PROBE_TIMEOUT)
        if probe_timeout is None:
            return None

        require_endpoint_info_raw = self.config.get("require_endpoint_info", True)
        if not isinstance(require_endpoint_info_raw, bool):
            self.set_failed(
                f"`require_endpoint_info` must be a boolean, got "
                f"{type(require_endpoint_info_raw).__name__}: {require_endpoint_info_raw!r}"
            )
            return None

        return {
            "cluster_name": cluster_name,
            "namespace": namespace,
            "authorized_probe_cmd": authorized,
            "unauthorized_probe_cmd": unauthorized,
            "probe_timeout": probe_timeout,
            "require_endpoint_info": require_endpoint_info_raw,
        }

    def _read_endpoint(self, cluster_name: str, namespace: str) -> str | None:
        """Read ``spec.controlPlaneEndpoint`` from the CAPI Cluster resource.

        Returns ``"host:port"`` on success, or ``None`` after calling
        ``set_failed`` if the Cluster is unreachable or the endpoint is empty.
        """
        kubectl_base = get_kubectl_base_shell()
        jsonpath = "{.spec.controlPlaneEndpoint.host}:{.spec.controlPlaneEndpoint.port}"
        cmd = (
            f"{kubectl_base} get cluster {shlex.quote(cluster_name)} "
            f"-n {shlex.quote(namespace)} -o jsonpath={shlex.quote(jsonpath)}"
        )
        result = self.run_command(cmd)
        if result.exit_code != 0:
            detail = result.stderr.strip() or result.stdout.strip() or f"exit code {result.exit_code}"
            self.set_failed(
                f"Unable to read Cluster {cluster_name!r} in namespace "
                f"{namespace!r}: {detail}. Verify the CAPI Cluster exists and "
                f"the management cluster is reachable, or set "
                f"`require_endpoint_info: false` to skip this read."
            )
            return None
        raw = result.stdout.strip()
        # jsonpath with two missing components renders as ":" — treat that as
        # "endpoint not populated yet" rather than a valid host:port.
        if not raw or raw == ":":
            self.set_failed(
                f"Cluster {cluster_name!r} in namespace {namespace!r} has no "
                f"`spec.controlPlaneEndpoint` populated — the control plane "
                f"has not yet been provisioned, or this infra provider does "
                f"not surface the endpoint here. Set "
                f"`require_endpoint_info: false` if this is expected."
            )
            return None
        return raw

    def _run_authorized_probe(self, authorized_probe_cmd: str, probe_timeout: int) -> bool:
        """Run the authorized baseline probe and report failure on non-zero exit.

        Returns ``True`` if the probe succeeded, or ``False`` after calling
        ``set_failed`` — a failing baseline makes the unauthorized-probe result
        ambiguous, so the check must stop before interpreting it.
        """
        result = self.run_command(authorized_probe_cmd, timeout=probe_timeout)
        if result.exit_code != 0:
            detail = result.stderr.strip() or result.stdout.strip() or f"exit code {result.exit_code}"
            snippet = truncate(authorized_probe_cmd)
            self.set_failed(
                f"Authorized probe failed (cmd: {snippet}): {detail}. A failing "
                f"baseline makes the unauthorized-probe result unreliable (could "
                f"mean 'ACL works' OR 'API is down'). Fix cluster access first, "
                f"then re-run."
            )
            return False
        return True

    def _run_unauthorized_probe(
        self,
        unauthorized_probe_cmd: str,
        probe_timeout: int,
        endpoint_info: str | None,
    ) -> None:
        """Run the unauthorized probe and set the final pass/fail verdict.

        A non-zero exit (connection blocked or timeout) means the ACL is
        enforced; a zero exit means the endpoint is reachable from a source
        that should be blocked and the check fails.
        """
        result = self.run_command(unauthorized_probe_cmd, timeout=probe_timeout)
        snippet = truncate(unauthorized_probe_cmd)
        endpoint_clause = f" (endpoint: {endpoint_info})" if endpoint_info else ""

        # 126/127 are shell conventions for "not executable" / "command not
        # found". Treating them as an ACL-enforced pass would hide a broken
        # probe and yield false assurance.
        if result.exit_code in (126, 127):
            detail = result.stderr.strip() or result.stdout.strip() or f"exit code {result.exit_code}"
            self.set_failed(
                f"Unauthorized probe could not execute{endpoint_clause} "
                f"(cmd: {snippet}): {detail}. Fix the probe tooling/command "
                f"and re-run."
            )
            return

        if result.exit_code == 0:
            preview = result.stdout.strip() or result.stderr.strip() or "(no output)"
            preview = truncate(preview, limit=120)
            self.set_failed(
                f"Unauthorized probe unexpectedly succeeded{endpoint_clause}: "
                f"the API endpoint is reachable from a source that should be "
                f"blocked, so no network ACL is in place. Probe cmd: {snippet}. "
                f"Probe output: {preview!r}."
            )
            return

        self.set_passed(
            f"API endpoint{endpoint_clause} blocked the unauthorized probe "
            f"(exit={result.exit_code}) and served the authorized probe — network "
            f"ACL verified."
        )
