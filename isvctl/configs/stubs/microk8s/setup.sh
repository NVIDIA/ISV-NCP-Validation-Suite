#!/bin/bash
# MicroK8s Inventory Stub - Queries local MicroK8s cluster
#
# Requirements:
#   - MicroK8s installed and running
#   - microk8s kubectl or kubectl configured
#
# Output: JSON inventory conforming to isvctl schema

set -eo pipefail

# Determine kubectl command (microk8s or regular)
if command -v microk8s &> /dev/null; then
    KUBECTL="microk8s kubectl"
elif command -v kubectl &> /dev/null; then
    KUBECTL="kubectl"
else
    echo "Error: Neither microk8s nor kubectl found" >&2
    exit 1
fi

# Check cluster is accessible
if ! $KUBECTL cluster-info &> /dev/null 2>&1; then
    echo "Error: Cannot connect to MicroK8s cluster" >&2
    exit 1
fi

# Get cluster name
CLUSTER_NAME="microk8s-$(hostname)"

# Get node count (usually 1 for local microk8s)
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
GPU_OPERATOR_NS="${GPU_OPERATOR_NS:-gpu-operator-resources}"

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
