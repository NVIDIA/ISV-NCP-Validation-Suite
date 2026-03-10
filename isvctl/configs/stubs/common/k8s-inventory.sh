#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

# Shared Kubernetes GPU Cluster Inventory
#
# Collects cluster inventory using kubectl (works on any K8s distribution).
# Sourced by provider-specific setup scripts. Sets shell variables that
# the caller uses to build its JSON output.
#
# Prerequisites: kubectl configured, jq available
#
# Variables set by this script:
#   NODE_COUNT, NODES (JSON array)
#   GPU_NODE_COUNT, GPU_PER_NODE, TOTAL_GPUS
#   GPU_OPERATOR_NS
#   DRIVER_VERSION
#   RUNTIME_CLASS
#   GPU_PRODUCT
#   API_SERVER, KUBECONFIG_PATH

# -----------------------------------------------------------------------------
# Dependency Checks
# -----------------------------------------------------------------------------

for cmd in kubectl jq; do
    if ! command -v "$cmd" &> /dev/null; then
        echo "Error: $cmd not found" >&2
        exit 1
    fi
done

if ! kubectl cluster-info &> /dev/null; then
    echo "Error: Cannot connect to cluster. Check KUBECONFIG." >&2
    exit 1
fi

echo "Connected to cluster." >&2

# -----------------------------------------------------------------------------
# Cluster Info
# -----------------------------------------------------------------------------

API_SERVER=$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}' 2>/dev/null || echo "")
KUBECONFIG_PATH="${KUBECONFIG:-$HOME/.kube/config}"

# -----------------------------------------------------------------------------
# Node Inventory
# -----------------------------------------------------------------------------

NODE_COUNT=$(kubectl get nodes --no-headers 2>/dev/null | wc -l | tr -d ' ')
NODES=$(kubectl get nodes -o json 2>/dev/null | jq '[.items[] | {
    name: .metadata.name,
    ready: (.status.conditions[] | select(.type=="Ready") | .status == "True"),
    gpus: (if .status.capacity["nvidia.com/gpu"] then (.status.capacity["nvidia.com/gpu"] | tonumber) else 0 end)
}]' 2>/dev/null || echo '[]')

echo "Nodes: ${NODE_COUNT}" >&2

# -----------------------------------------------------------------------------
# GPU Inventory
# -----------------------------------------------------------------------------

GPU_NODE_COUNT=$(kubectl get nodes -l nvidia.com/gpu.present=true --no-headers 2>/dev/null | wc -l | tr -d ' ')
GPU_PER_NODE=$(kubectl get nodes -l nvidia.com/gpu.present=true -o jsonpath='{.items[0].status.capacity.nvidia\.com/gpu}' 2>/dev/null || echo "0")
GPU_PER_NODE=${GPU_PER_NODE:-0}
[ -z "$GPU_PER_NODE" ] || [ "$GPU_PER_NODE" = "null" ] && GPU_PER_NODE=0
TOTAL_GPUS=$((GPU_NODE_COUNT * GPU_PER_NODE))

echo "GPU nodes: ${GPU_NODE_COUNT}, GPUs per node: ${GPU_PER_NODE}, Total: ${TOTAL_GPUS}" >&2

# -----------------------------------------------------------------------------
# GPU Operator Namespace (check common conventions)
# -----------------------------------------------------------------------------

GPU_OPERATOR_NS="${GPU_OPERATOR_NS:-}"
if [ -z "$GPU_OPERATOR_NS" ]; then
    for ns in nvidia-gpu-operator gpu-operator gpu-operator-resources openshift-operators; do
        if kubectl get namespace "$ns" &> /dev/null; then
            POD_COUNT=$(kubectl get pods -n "$ns" -l app=gpu-operator --no-headers 2>/dev/null | wc -l | tr -d ' ')
            if [ "${POD_COUNT}" -gt 0 ]; then
                GPU_OPERATOR_NS="$ns"
                break
            fi
        fi
    done
    GPU_OPERATOR_NS="${GPU_OPERATOR_NS:-gpu-operator}"
fi

echo "GPU Operator namespace: ${GPU_OPERATOR_NS}" >&2

# -----------------------------------------------------------------------------
# Driver Version
# -----------------------------------------------------------------------------

DRIVER_MAJOR=$(kubectl get nodes -l nvidia.com/gpu.present=true -o jsonpath='{.items[0].metadata.labels.nvidia\.com/cuda\.driver\.major}' 2>/dev/null || echo "")
DRIVER_MINOR=$(kubectl get nodes -l nvidia.com/gpu.present=true -o jsonpath='{.items[0].metadata.labels.nvidia\.com/cuda\.driver\.minor}' 2>/dev/null || echo "")
DRIVER_REV=$(kubectl get nodes -l nvidia.com/gpu.present=true -o jsonpath='{.items[0].metadata.labels.nvidia\.com/cuda\.driver\.rev}' 2>/dev/null || echo "")

if [ -n "$DRIVER_MAJOR" ] && [ -n "$DRIVER_MINOR" ] && [ -n "$DRIVER_REV" ]; then
    DRIVER_VERSION="${DRIVER_MAJOR}.${DRIVER_MINOR}.${DRIVER_REV}"
elif [ -n "$DRIVER_MAJOR" ] && [ -n "$DRIVER_MINOR" ]; then
    DRIVER_VERSION="${DRIVER_MAJOR}.${DRIVER_MINOR}"
else
    DRIVER_VERSION=""
fi

# -----------------------------------------------------------------------------
# RuntimeClass
# -----------------------------------------------------------------------------

RUNTIME_CLASS="${RUNTIME_CLASS:-}"
if [ -z "$RUNTIME_CLASS" ]; then
    kubectl get runtimeclass nvidia &> /dev/null 2>&1 && RUNTIME_CLASS="nvidia"
fi

# -----------------------------------------------------------------------------
# GPU Product Info
# -----------------------------------------------------------------------------

GPU_PRODUCT=$(kubectl get nodes -l nvidia.com/gpu.present=true -o jsonpath='{.items[0].metadata.labels.nvidia\.com/gpu\.product}' 2>/dev/null || echo "")

echo "Driver: ${DRIVER_VERSION}, GPU: ${GPU_PRODUCT}, RuntimeClass: ${RUNTIME_CLASS:-none}" >&2
