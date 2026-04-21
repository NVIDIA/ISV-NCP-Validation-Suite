#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

# Slurm Inventory Stub - Queries real Slurm cluster and outputs inventory JSON
#
# Requirements:
#   - Slurm commands (sinfo, scontrol) accessible
#   - jq for JSON processing
#
# Output: JSON inventory conforming to isvctl schema

set -eo pipefail

# Check sinfo is available
if ! command -v sinfo &> /dev/null; then
    echo "Error: sinfo not found - Slurm not available" >&2
    exit 1
fi

# Check jq is available
if ! command -v jq &> /dev/null; then
    echo "Error: jq not found - required for JSON processing" >&2
    exit 1
fi

# Get cluster name
CLUSTER_NAME=$(scontrol show config 2>/dev/null | grep -E "^ClusterName\s*=" | awk -F'=' '{print $2}' | tr -d ' ' || echo "slurm-cluster")

# Get default partition (marked with *)
DEFAULT_PARTITION=$(sinfo -h -o "%P" 2>/dev/null | grep '\*' | tr -d '*' | head -1)
if [ -z "$DEFAULT_PARTITION" ]; then
    DEFAULT_PARTITION=$(sinfo -h -o "%P" 2>/dev/null | tr -d '*' | head -1)
fi

# Build partitions object with node lists
# Get all partition names
PARTITIONS_JSON="{"
FIRST=true
for partition in $(sinfo -h -o "%P" 2>/dev/null | tr -d '*' | sort -u); do
    # Get nodes in this partition
    NODES=$(sinfo -h -p "$partition" -N -o "%N" 2>/dev/null | sort -u | jq -R . | jq -s .)

    if [ "$FIRST" = true ]; then
        FIRST=false
    else
        PARTITIONS_JSON+=","
    fi
    PARTITIONS_JSON+="\"$partition\":{\"nodes\":$NODES}"
done
PARTITIONS_JSON+="}"

# Get GPU partition info (look for partition with GPUs)
GPU_PARTITION=""
GPU_PER_NODE=0
TOTAL_GPUS=0

for partition in $(sinfo -h -o "%P" 2>/dev/null | tr -d '*' | sort -u); do
    GPU_GRES=$(sinfo -h -p "$partition" -o "%G" 2>/dev/null | head -1 || echo "")
    if [[ "$GPU_GRES" =~ gpu ]]; then
        GPU_PARTITION="$partition"
        # Extract GPU count per node
        if [[ "$GPU_GRES" =~ gpu:([0-9]+) ]]; then
            GPU_PER_NODE="${BASH_REMATCH[1]}"
        elif [[ "$GPU_GRES" =~ gpu:[^:]+:([0-9]+) ]]; then
            GPU_PER_NODE="${BASH_REMATCH[1]}"
        fi
        # Get node count in GPU partition
        GPU_NODE_COUNT=$(sinfo -h -p "$partition" -o "%D" 2>/dev/null | head -1 || echo "0")
        TOTAL_GPUS=$((GPU_NODE_COUNT * GPU_PER_NODE))
        break
    fi
done

# Get CUDA architecture (try nvidia-smi if available)
CUDA_ARCH=""
if command -v nvidia-smi &> /dev/null; then
    # Get compute capability (e.g., "8.0" for A100, "9.0" for H100)
    COMPUTE_CAP=$(nvidia-smi --query-gpu=compute_capability --format=csv,noheader 2>/dev/null | head -1 || echo "")
    if [ -n "$COMPUTE_CAP" ]; then
        # Convert "8.0" to "80", "9.0" to "90"
        CUDA_ARCH=$(echo "$COMPUTE_CAP" | tr -d '.')
    fi
fi

# Get driver version
DRIVER_VERSION="unknown"
if command -v nvidia-smi &> /dev/null; then
    DRIVER_VERSION=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1 || echo "unknown")
fi

# Storage path (check common locations)
STORAGE_PATH="/tmp"
for path in /scratch /lustre /gpfs /home; do
    if [ -d "$path" ] && [ -w "$path" ]; then
        STORAGE_PATH="$path"
        break
    fi
done

# Use GPU partition as default if available, otherwise use detected default
if [ -n "$GPU_PARTITION" ]; then
    DEFAULT_PARTITION="$GPU_PARTITION"
fi

# Output JSON
cat << EOF
{
  "success": true,
  "platform": "slurm",
  "cluster_name": "${CLUSTER_NAME}",
  "slurm": {
    "partitions": ${PARTITIONS_JSON},
    "cuda_arch": "${CUDA_ARCH}",
    "storage_path": "${STORAGE_PATH}",
    "default_partition": "${DEFAULT_PARTITION}",
    "driver_version": "${DRIVER_VERSION}",
    "gpu_per_node": ${GPU_PER_NODE},
    "total_gpus": ${TOTAL_GPUS}
  }
}
EOF
