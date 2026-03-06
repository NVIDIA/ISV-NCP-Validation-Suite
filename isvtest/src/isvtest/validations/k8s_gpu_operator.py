# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

import shlex
from typing import ClassVar

from isvtest.config.settings import get_k8s_gpu_operator_namespace
from isvtest.core.k8s import get_kubectl_command
from isvtest.core.validation import BaseValidation


class K8sGpuOperatorNamespaceCheck(BaseValidation):
    description = "Verify GPU Operator namespace exists."
    markers: ClassVar[list[str]] = ["kubernetes"]

    def run(self) -> None:
        # Prefer config value, fall back to global setting
        namespace = self.config.get("namespace") or get_k8s_gpu_operator_namespace()

        kubectl_parts = get_kubectl_command()
        kubectl_base = " ".join(shlex.quote(part) for part in kubectl_parts)

        result = self.run_command(f"{kubectl_base} get namespace {shlex.quote(namespace)}")

        if result.exit_code != 0:
            self.set_failed(f"GPU Operator namespace '{namespace}' not found: {result.stderr}")
            return

        self.set_passed(f"GPU Operator namespace '{namespace}' exists")


class K8sGpuOperatorPodsCheck(BaseValidation):
    description = "Check if NVIDIA GPU Operator pods are running."
    markers: ClassVar[list[str]] = ["kubernetes"]

    def run(self) -> None:
        # Prefer config value, fall back to global setting
        namespace = self.config.get("namespace") or get_k8s_gpu_operator_namespace()

        kubectl_parts = get_kubectl_command()
        kubectl_base = " ".join(shlex.quote(part) for part in kubectl_parts)

        result = self.run_command(f"{kubectl_base} get pods -n {shlex.quote(namespace)}")

        if result.exit_code != 0:
            self.set_failed(f"Failed to get GPU Operator pods: {result.stderr}")
            return

        # Parse kubectl output - STATUS is the 3rd column (index 2)
        # Format: NAME  READY  STATUS  RESTARTS  AGE
        running_pods = []
        for line in result.stdout.split("\n"):
            columns = line.split()
            # Skip header and empty lines, check STATUS column exactly equals "Running"
            if len(columns) >= 3 and columns[2] == "Running":
                running_pods.append(columns[0])  # Store pod name

        if not running_pods:
            self.set_failed(f"No GPU Operator pods are running in namespace '{namespace}'")
            return

        self.set_passed(f"Found {len(running_pods)} running pods in '{namespace}'")
