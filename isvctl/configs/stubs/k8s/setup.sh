#!/bin/bash
# K8s Inventory Stub - Queries real cluster and outputs inventory JSON
# This stub queries kubectl to dynamically generate cluster inventory
#
# Requirements:
#   - kubectl OR microk8s configured and accessible
#   - jq for JSON processing
#   - nvidia GPU operator installed (for GPU detection)
#
# Output: JSON inventory conforming to isvctl schema

set -eo pipefail

# Check jq is available
if ! command -v jq &> /dev/null; then
    echo "Error: jq not found - required for JSON processing" >&2
    exit 1
fi

# Detect kubectl command (regular kubectl or microk8s)
if command -v kubectl &> /dev/null; then
    KUBECTL="kubectl"
elif command -v microk8s &> /dev/null; then
    KUBECTL="microk8s kubectl"
else
    echo "Error: Neither kubectl nor microk8s found" >&2
    exit 1
fi

# Check cluster is accessible
if ! $KUBECTL cluster-info &> /dev/null 2>&1; then
    echo "Error: Cannot connect to Kubernetes cluster (using: $KUBECTL)" >&2
    exit 1
fi

# Get cluster name (from context or first node)
CLUSTER_NAME=$($KUBECTL config current-context 2>/dev/null || echo "unknown")

# Get node information
NODE_COUNT=$($KUBECTL get nodes --no-headers 2>/dev/null | wc -l)

# Get node names as JSON array
NODES=$($KUBECTL get nodes -o jsonpath='{.items[*].metadata.name}' 2>/dev/null | tr ' ' '\n' | jq -R . | jq -s .)

# Get GPU node count (nodes with nvidia.com/gpu.present=true label)
# Use -o name to avoid counting "No resources found" message
GPU_NODE_COUNT=$($KUBECTL get nodes -l nvidia.com/gpu.present=true -o name 2>/dev/null | wc -l || echo "0")

# Get GPU count per node (from first GPU node)
GPU_PER_NODE=$($KUBECTL get nodes -l nvidia.com/gpu.present=true -o jsonpath='{.items[0].status.capacity.nvidia\.com/gpu}' 2>/dev/null || echo "0")
if [ -z "$GPU_PER_NODE" ] || [ "$GPU_PER_NODE" = "null" ]; then
    GPU_PER_NODE=0
fi

# Calculate total GPUs
TOTAL_GPUS=$((GPU_NODE_COUNT * GPU_PER_NODE))

# Get GPU operator namespace (look for common namespaces)
GPU_OPERATOR_NS=""
for ns in gpu-operator gpu-operator-resources nvidia-gpu-operator; do
    if $KUBECTL get namespace "$ns" &> /dev/null 2>&1; then
        GPU_OPERATOR_NS="$ns"
        break
    fi
done
GPU_OPERATOR_NS="${GPU_OPERATOR_NS:-unknown}"

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
else
    DRIVER_VERSION="unknown"
fi

# Detect runtime class (only set if it exists)
RUNTIME_CLASS=""
if $KUBECTL get runtimeclass nvidia &> /dev/null 2>&1; then
    RUNTIME_CLASS="nvidia"
fi

# GPU resource name
GPU_RESOURCE_NAME="nvidia.com/gpu"

# Output JSON
cat << EOF
{
  "success": true,
  "platform": "kubernetes",
  "cluster_name": "${CLUSTER_NAME}",
  "kubernetes": {
    "driver_version": "${DRIVER_VERSION}",
    "node_count": ${NODE_COUNT},
    "nodes": ${NODES},
    "gpu_node_count": ${GPU_NODE_COUNT},
    "gpu_per_node": ${GPU_PER_NODE},
    "total_gpus": ${TOTAL_GPUS},
    "gpu_operator_namespace": "${GPU_OPERATOR_NS}",
    "runtime_class": "${RUNTIME_CLASS}",
    "gpu_resource_name": "${GPU_RESOURCE_NAME}"
  }
}
EOF
