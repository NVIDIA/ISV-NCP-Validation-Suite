#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

# Bare Metal Inventory Stub - Queries local system and outputs inventory JSON
#
# Requirements:
#   - nvidia-smi for GPU detection
#
# Output: JSON inventory conforming to isvctl schema

set -eo pipefail

# Get hostname
HOSTNAME=$(hostname -s 2>/dev/null || echo "localhost")

# Default values
GPU_COUNT=0
DRIVER_VERSION="unknown"
CUDA_VERSION="unknown"

# Check nvidia-smi is available
if command -v nvidia-smi &> /dev/null; then
    # Get GPU count by listing indices (more portable than --query-gpu=count)
    GPU_COUNT=$(nvidia-smi --query-gpu=index --format=csv,noheader 2>/dev/null | wc -l || echo "0")

    # Get driver version
    DRIVER_VERSION=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1 || echo "unknown")

    # Get CUDA version from nvidia-smi header
    CUDA_VERSION=$(nvidia-smi 2>/dev/null | grep "CUDA Version" | awk '{print $9}' || echo "unknown")
else
    echo "Warning: nvidia-smi not found - GPU detection unavailable" >&2
fi

# Output JSON
cat << EOF
{
  "success": true,
  "platform": "bare_metal",
  "cluster_name": "${HOSTNAME}",
  "bare_metal": {
    "hostname": "${HOSTNAME}",
    "gpu_count": ${GPU_COUNT},
    "driver_version": "${DRIVER_VERSION}",
    "cuda_version": "${CUDA_VERSION}"
  }
}
EOF
