#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Exercise Kubernetes node cordoning semantics for BFX01-04."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
import uuid
from typing import Any

DEFAULT_IMAGE = "registry.k8s.io/pause:3.10"


class CordonTestError(RuntimeError):
    """Raised when the cordon workflow cannot prove the required behavior."""


def _kubectl_command() -> list[str]:
    """Return the configured kubectl-compatible command prefix."""
    configured = os.environ.get("KUBECTL", "kubectl")
    try:
        command = shlex.split(configured)
    except ValueError as exc:
        raise CordonTestError(f"Invalid KUBECTL value: {exc}") from exc
    if not command:
        raise CordonTestError("KUBECTL must not be blank")
    return command


def _run(
    kubectl: list[str],
    *args: str,
    input_text: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run kubectl and raise a concise error when the command fails."""
    try:
        completed = subprocess.run(
            [*kubectl, *args],
            input=input_text,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise CordonTestError(f"Unable to run {' '.join(kubectl)}: {exc}") from exc
    if check and completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        detail = detail[-500:] if detail else "command failed without output"
        raise CordonTestError(f"kubectl {' '.join(args)} failed: {detail}")
    return completed


def _json_output(completed: subprocess.CompletedProcess[str], resource: str) -> dict[str, Any]:
    """Parse one kubectl JSON object."""
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise CordonTestError(f"kubectl returned invalid JSON for {resource}") from exc
    if not isinstance(payload, dict):
        raise CordonTestError(f"kubectl returned a non-object for {resource}")
    return payload


def _node_is_ready(node: dict[str, Any]) -> bool:
    """Return whether a node is Ready, schedulable, and available for the test."""
    conditions = node.get("status", {}).get("conditions", [])
    ready = any(item.get("type") == "Ready" and item.get("status") == "True" for item in conditions)
    return ready and not node.get("spec", {}).get("unschedulable", False)


def _select_node(kubectl: list[str], requested_node: str | None) -> tuple[str, str, list[dict[str, str]]]:
    """Select a schedulable Ready node and return its identity and required tolerations."""
    payload = _json_output(_run(kubectl, "get", "nodes", "-o", "json"), "node list")
    items = payload.get("items")
    if not isinstance(items, list):
        raise CordonTestError("kubectl node list is missing items")

    candidates = [node for node in items if isinstance(node, dict) and _node_is_ready(node)]
    if requested_node:
        candidates = [node for node in candidates if node.get("metadata", {}).get("name") == requested_node]
        if not candidates:
            raise CordonTestError(f"Requested node {requested_node!r} is not Ready and schedulable")
    if not candidates:
        raise CordonTestError("No Ready, schedulable node is available for the cordon test")

    node = candidates[0]
    metadata = node.get("metadata", {})
    name = metadata.get("name")
    hostname = metadata.get("labels", {}).get("kubernetes.io/hostname")
    if not isinstance(name, str) or not name:
        raise CordonTestError("Selected node is missing metadata.name")
    if not isinstance(hostname, str) or not hostname:
        raise CordonTestError(f"Node {name!r} is missing the kubernetes.io/hostname label")
    tolerations = []
    for taint in node.get("spec", {}).get("taints", []):
        key = taint.get("key")
        effect = taint.get("effect")
        if not isinstance(key, str) or effect not in {"NoSchedule", "NoExecute"}:
            continue
        if key == "node.kubernetes.io/unschedulable":
            continue
        tolerations.append(
            {
                "key": key,
                "operator": "Equal",
                "value": str(taint.get("value", "")),
                "effect": effect,
            }
        )
    return name, hostname, tolerations


def _pod_manifest(
    name: str,
    namespace: str,
    hostname: str,
    image: str,
    tolerations: list[dict[str, str]],
) -> str:
    """Build a minimal long-running pod constrained to one node hostname."""
    return json.dumps(
        {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": name,
                "namespace": namespace,
                "labels": {
                    "app.kubernetes.io/managed-by": "isvtest",
                    "isvtest.nvidia.com/purpose": "bfx01-04",
                },
            },
            "spec": {
                "restartPolicy": "Never",
                "nodeSelector": {"kubernetes.io/hostname": hostname},
                "tolerations": tolerations,
                "containers": [{"name": "probe", "image": image}],
            },
        }
    )


def _get_pod(kubectl: list[str], namespace: str, name: str) -> dict[str, Any]:
    """Return one pod as a JSON object."""
    completed = _run(kubectl, "get", "pod", name, "-n", namespace, "-o", "json")
    return _json_output(completed, f"pod {namespace}/{name}")


def _pod_is_ready_on_node(pod: dict[str, Any], node_name: str) -> bool:
    """Return whether a pod is still Ready and bound to the expected node."""
    if pod.get("spec", {}).get("nodeName") != node_name or pod.get("status", {}).get("phase") != "Running":
        return False
    conditions = pod.get("status", {}).get("conditions", [])
    return any(item.get("type") == "Ready" and item.get("status") == "True" for item in conditions)


def _pod_is_unschedulable(pod: dict[str, Any]) -> bool:
    """Return whether the scheduler explicitly reported the pod unschedulable."""
    if pod.get("spec", {}).get("nodeName"):
        return False
    conditions = pod.get("status", {}).get("conditions", [])
    return any(
        item.get("type") == "PodScheduled" and item.get("status") == "False" and item.get("reason") == "Unschedulable"
        for item in conditions
    )


def _wait_for_unschedulable(
    kubectl: list[str],
    namespace: str,
    name: str,
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> bool:
    """Poll until Kubernetes reports that the new probe cannot be scheduled."""
    deadline = time.monotonic() + timeout_seconds
    while True:
        if _pod_is_unschedulable(_get_pod(kubectl, namespace, name)):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll_interval_seconds)


def _cleanup(kubectl: list[str], namespace: str, pod_names: list[str], node_name: str | None) -> list[str]:
    """Delete probe pods and restore node schedulability, returning any errors."""
    errors: list[str] = []
    for pod_name in pod_names:
        try:
            completed = _run(
                kubectl,
                "delete",
                "pod",
                pod_name,
                "-n",
                namespace,
                "--ignore-not-found=true",
                "--wait=false",
                check=False,
            )
        except CordonTestError as exc:
            errors.append(f"delete pod {namespace}/{pod_name}: {exc}")
            continue
        if completed.returncode != 0:
            errors.append(f"delete pod {namespace}/{pod_name}: {(completed.stderr or completed.stdout).strip()}")
    if node_name:
        try:
            completed = _run(kubectl, "uncordon", node_name, check=False)
        except CordonTestError as exc:
            errors.append(f"uncordon node {node_name}: {exc}")
        else:
            if completed.returncode != 0:
                errors.append(f"uncordon node {node_name}: {(completed.stderr or completed.stdout).strip()}")
    return errors


def _parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(description="Cordon a node and verify Kubernetes scheduling behavior")
    parser.add_argument("--region", default="", help="Accepted for provider config compatibility")
    parser.add_argument("--node", help="Specific Ready, schedulable node to test")
    parser.add_argument("--namespace", default="default", help="Namespace for temporary probe pods")
    parser.add_argument("--image", default=DEFAULT_IMAGE, help="Container image for temporary probe pods")
    parser.add_argument("--timeout-seconds", type=float, default=120, help="Timeout for each scheduling assertion")
    parser.add_argument("--poll-interval-seconds", type=float, default=2, help="Pending-pod polling interval")
    return parser


def main() -> int:
    """Run the reversible cordon test and emit its provider-neutral JSON result."""
    args = _parser().parse_args()
    operation: dict[str, Any] = {
        "cordoned": False,
        "new_workloads_blocked": False,
        "existing_workloads_running": False,
    }
    result: dict[str, Any] = {"success": False, "platform": "my-isv", "test_name": "cordon_node"}
    kubectl: list[str] = []
    created_pods: list[str] = []
    cordoned_node: str | None = None

    try:
        if args.timeout_seconds <= 0 or args.poll_interval_seconds <= 0:
            raise CordonTestError("Timeout and poll interval must be greater than zero")
        kubectl = _kubectl_command()
        node_name, hostname, tolerations = _select_node(kubectl, args.node)
        operation["node_id"] = node_name
        suffix = uuid.uuid4().hex[:8]
        existing_pod = f"isvtest-bfx-existing-{suffix}"
        blocked_pod = f"isvtest-bfx-blocked-{suffix}"

        _run(
            kubectl,
            "create",
            "-f",
            "-",
            input_text=_pod_manifest(existing_pod, args.namespace, hostname, args.image, tolerations),
        )
        created_pods.append(existing_pod)
        _run(
            kubectl,
            "wait",
            "--for=condition=Ready",
            f"pod/{existing_pod}",
            "-n",
            args.namespace,
            f"--timeout={args.timeout_seconds:g}s",
        )

        _run(kubectl, "cordon", node_name)
        cordoned_node = node_name
        node = _json_output(_run(kubectl, "get", "node", node_name, "-o", "json"), f"node {node_name}")
        operation["cordoned"] = node.get("spec", {}).get("unschedulable") is True
        if not operation["cordoned"]:
            raise CordonTestError(f"Node {node_name!r} was not marked unschedulable")

        operation["existing_workloads_running"] = _pod_is_ready_on_node(
            _get_pod(kubectl, args.namespace, existing_pod), node_name
        )
        if not operation["existing_workloads_running"]:
            raise CordonTestError("Existing probe pod did not remain Ready on the cordoned node")

        _run(
            kubectl,
            "create",
            "-f",
            "-",
            input_text=_pod_manifest(blocked_pod, args.namespace, hostname, args.image, tolerations),
        )
        created_pods.append(blocked_pod)
        operation["new_workloads_blocked"] = _wait_for_unschedulable(
            kubectl,
            args.namespace,
            blocked_pod,
            args.timeout_seconds,
            args.poll_interval_seconds,
        )
        if not operation["new_workloads_blocked"]:
            raise CordonTestError("New probe pod was not confirmed unschedulable on the cordoned node")
        result["success"] = True
    except CordonTestError as exc:
        result["error"] = str(exc)
    finally:
        cleanup_errors = _cleanup(kubectl, args.namespace, created_pods, cordoned_node) if kubectl else []
        if cleanup_errors:
            result["success"] = False
            result["cleanup_errors"] = cleanup_errors
            result.setdefault("error", "Cordon test cleanup failed")

    result["operation"] = operation
    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
