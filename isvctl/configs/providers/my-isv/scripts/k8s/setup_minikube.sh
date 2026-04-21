#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

# Minikube Inventory Stub - Queries local Minikube cluster
#
# Requirements:
#   - Minikube installed and running
#   - kubectl configured (minikube automatically configures kubeconfig)

set -eo pipefail

# Detect kubectl command
if [[ "${KUBECTL:-}" =~ [^[:space:]] ]]; then
    :  # already set from environment; skip detection
elif command -v kubectl &> /dev/null; then
    KUBECTL="kubectl"
else
    echo "Error: kubectl not found. Set KUBECTL to override." >&2
    exit 1
fi

# Get cluster name from minikube profile or kubectl context
if command -v minikube &> /dev/null; then
    CLUSTER_NAME=$(minikube profile 2>/dev/null || echo "minikube")
else
    CLUSTER_NAME=$($KUBECTL config current-context 2>/dev/null || echo "minikube")
fi

DEFAULT_GPU_NS="${DEFAULT_GPU_NS:-gpu-operator}"
USE_NVIDIA_SMI_FALLBACK="${USE_NVIDIA_SMI_FALLBACK:-true}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_common.sh"
