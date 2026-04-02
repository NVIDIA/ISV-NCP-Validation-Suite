#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

# k3s Inventory Stub - Queries local k3s cluster
#
# Requirements:
#   - k3s installed and running
#   - kubectl or k3s kubectl available
#   - KUBECONFIG set or /etc/rancher/k3s/k3s.yaml readable
#
# Output: JSON inventory conforming to isvctl schema

set -eo pipefail

# Determine kubectl command (k3s kubectl or regular kubectl)
if command -v kubectl &> /dev/null; then
    KUBECTL="kubectl"
elif command -v k3s &> /dev/null; then
    KUBECTL="k3s kubectl"
else
    echo "Error: Neither kubectl nor k3s found" >&2
    exit 1
fi

# Set KUBECONFIG for k3s if not already set and default config exists
if [ -z "$KUBECONFIG" ] && [ -f /etc/rancher/k3s/k3s.yaml ]; then
    export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
fi

# Check cluster is accessible
if ! $KUBECTL cluster-info &> /dev/null 2>&1; then
    echo "Error: Cannot connect to k3s cluster. Is it running? (sudo systemctl status k3s)" >&2
    exit 1
fi

# Get cluster name
CLUSTER_NAME="k3s-$(hostname)"

# Get node count (usually 1 for local k3s)
NODE_COUNT=$($KUBECTL get nodes --no-headers 2>/dev/null | wc -l)

# Get GPU info (use -o name to avoid counting "No resources found" message)
GPU_NODE_COUNT=$($KUBECTL get nodes -l nvidia.com/gpu.present=true -o name 2>/dev/null | wc -l || echo "0")
GPU_PER_NODE=$($KUBECTL get nodes -l nvidia.com/gpu.present=true -o jsonpath='{.items[0].status.capacity.nvidia\.com/gpu}' 2>/dev/null || echo "0")
if [ -z "$GPU_PER_NODE" ] || [ "$GPU_PER_NODE" = "null" ]; then
    # Fallback: count GPUs from nvidia-smi (one line per GPU)
    if command -v nvidia-smi &> /dev/null; then
        GPU_PER_NODE=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | wc -l || echo "0")
    else
        GPU_PER_NODE=0
    fi
fi

TOTAL_GPUS=$((GPU_NODE_COUNT * GPU_PER_NODE))

# Get driver version from node labels (combine major.minor.rev)
DRIVER_MAJOR=$($KUBECTL get nodes -l nvidia.com/gpu.present=true -o jsonpath='{.items[0].metadata.labels.nvidia\.com/cuda\.driver\.major}' 2>/dev/null || echo "")
DRIVER_MINOR=$($KUBECTL get nodes -l nvidia.com/gpu.present=true -o jsonpath='{.items[0].metadata.labels.nvidia\.com/cuda\.driver\.minor}' 2>/dev/null || echo "")
DRIVER_REV=$($KUBECTL get nodes -l nvidia.com/gpu.present=true -o jsonpath='{.items[0].metadata.labels.nvidia\.com/cuda\.driver\.rev}' 2>/dev/null || echo "")

if [ -n "$DRIVER_MAJOR" ] && [ -n "$DRIVER_MINOR" ] && [ -n "$DRIVER_REV" ]; then
    DRIVER_VERSION="${DRIVER_MAJOR}.${DRIVER_MINOR}.${DRIVER_REV}"
elif [ -n "$DRIVER_MAJOR" ] && [ -n "$DRIVER_MINOR" ]; then
    DRIVER_VERSION="${DRIVER_MAJOR}.${DRIVER_MINOR}"
elif [ -n "$DRIVER_MAJOR" ]; then
    DRIVER_VERSION="${DRIVER_MAJOR}"
elif command -v nvidia-smi &> /dev/null; then
    # Fallback to nvidia-smi if labels not available
    DRIVER_VERSION=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1 || echo "unknown")
else
    DRIVER_VERSION="unknown"
fi

# GPU operator namespace
GPU_OPERATOR_NS=""
for ns in gpu-operator gpu-operator-resources nvidia-gpu-operator; do
    if $KUBECTL get namespace "$ns" &> /dev/null 2>&1; then
        GPU_OPERATOR_NS="$ns"
        break
    fi
done
GPU_OPERATOR_NS="${GPU_OPERATOR_NS:-nvidia-gpu-operator}"

# Output JSON
cat << EOF
{
  "success": true,
  "platform": "kubernetes",
  "cluster_name": "${CLUSTER_NAME}",
  "kubernetes": {
    "driver_version": "${DRIVER_VERSION}",
    "node_count": ${NODE_COUNT},
    "nodes": [],
    "gpu_node_count": ${GPU_NODE_COUNT},
    "gpu_per_node": ${GPU_PER_NODE},
    "total_gpus": ${TOTAL_GPUS},
    "gpu_operator_namespace": "${GPU_OPERATOR_NS}",
    "runtime_class": "nvidia",
    "gpu_resource_name": "nvidia.com/gpu"
  }
}
EOF
