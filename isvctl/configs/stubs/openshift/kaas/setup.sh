#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

# OpenShift KaaS Setup - Query existing cluster inventory
#
# Sources the shared K8s inventory script for generic kubectl queries,
# then adds OpenShift-specific info (cluster version, infrastructure name).
#
# Requirements:
#   - kubectl and oc CLI configured and authenticated
#   - jq
#
# Output: JSON inventory conforming to isvctl cluster schema

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# OpenShift defaults (before sourcing shared script)
GPU_OPERATOR_NS="${GPU_OPERATOR_NS:-nvidia-gpu-operator}"

# Collect generic K8s inventory (sets NODE_COUNT, NODES, GPU_*, DRIVER_*, etc.)
# shellcheck source=../../common/k8s-inventory.sh
source "${SCRIPT_DIR}/../../common/k8s-inventory.sh"

# -----------------------------------------------------------------------------
# OpenShift-specific info (oc)
# -----------------------------------------------------------------------------

if command -v oc &> /dev/null; then
    CLUSTER_NAME=$(oc get infrastructure cluster -o jsonpath='{.status.infrastructureName}' 2>/dev/null || echo "openshift-cluster")
    OCP_VERSION=$(oc get clusterversion version -o jsonpath='{.status.desired.version}' 2>/dev/null || echo "")
    echo "OpenShift: ${OCP_VERSION} (${CLUSTER_NAME})" >&2
else
    CLUSTER_NAME="openshift-cluster"
    OCP_VERSION=""
fi

# OpenShift doesn't use RuntimeClass for GPU pods
RUNTIME_CLASS="${RUNTIME_CLASS:-}"

# -----------------------------------------------------------------------------
# Output JSON Inventory
# -----------------------------------------------------------------------------

cat << EOF
{
  "success": true,
  "platform": "kubernetes",
  "cluster_name": "${CLUSTER_NAME}",
  "node_count": ${NODE_COUNT},
  "endpoint": "${API_SERVER}",
  "gpu_count": ${TOTAL_GPUS},
  "gpu_per_node": ${GPU_PER_NODE},
  "driver_version": "${DRIVER_VERSION}",
  "kubeconfig_path": "${KUBECONFIG_PATH}",
  "kubernetes": {
    "driver_version": "${DRIVER_VERSION}",
    "node_count": ${NODE_COUNT},
    "nodes": ${NODES},
    "gpu_node_count": ${GPU_NODE_COUNT},
    "gpu_per_node": ${GPU_PER_NODE},
    "total_gpus": ${TOTAL_GPUS},
    "control_plane_address": "${API_SERVER}",
    "kubeconfig_path": "${KUBECONFIG_PATH}",
    "gpu_operator_namespace": "${GPU_OPERATOR_NS}",
    "runtime_class": "${RUNTIME_CLASS}",
    "gpu_resource_name": "nvidia.com/gpu"
  },
  "openshift": {
    "version": "${OCP_VERSION}",
    "cluster_name": "${CLUSTER_NAME}",
    "gpu_product": "${GPU_PRODUCT}"
  }
}
EOF
