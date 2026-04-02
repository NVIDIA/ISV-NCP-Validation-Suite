#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

# MicroK8s Inventory Stub - Queries local MicroK8s cluster
#
# Requirements:
#   - MicroK8s installed and running
#   - microk8s kubectl or kubectl configured

set -eo pipefail

# Detect kubectl command (microk8s or regular)
if command -v microk8s &> /dev/null; then
    KUBECTL="microk8s kubectl"
elif command -v kubectl &> /dev/null; then
    KUBECTL="kubectl"
else
    echo "Error: Neither microk8s nor kubectl found" >&2
    exit 1
fi

CLUSTER_NAME="microk8s-$(hostname)"
DEFAULT_GPU_NS="gpu-operator-resources"
USE_NVIDIA_SMI_FALLBACK="true"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_common.sh"
