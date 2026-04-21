#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

# K8s Inventory Stub - Queries real cluster and outputs inventory JSON
#
# Requirements:
#   - kubectl OR microk8s configured and accessible
#   - jq for JSON processing
#   - nvidia GPU operator installed (for GPU detection)

set -eo pipefail

# Detect kubectl command
if [[ "${KUBECTL:-}" =~ [^[:space:]] ]]; then
    :  # already set from environment; skip detection
elif command -v kubectl &> /dev/null; then
    KUBECTL="kubectl"
elif command -v microk8s &> /dev/null; then
    KUBECTL="microk8s kubectl"
else
    echo "Error: Neither kubectl nor microk8s found. Set KUBECTL to override." >&2
    exit 1
fi

CLUSTER_NAME=$($KUBECTL config current-context 2>/dev/null || echo "unknown")
DEFAULT_GPU_NS="unknown"
REQUIRE_JQ="true"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_common.sh"
