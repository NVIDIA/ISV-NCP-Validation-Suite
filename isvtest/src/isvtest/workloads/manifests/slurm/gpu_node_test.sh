#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

# GPU node test script for SlurmNodeJobExecution
# Tests: GPU access, storage write/read, optional GPU compute
#
# Variables:
#   STORAGE_PATH - Path for storage test (default: /tmp)
#   TEST_COMPUTE - "true" to run GPU compute test (default: true)

STORAGE_PATH="${STORAGE_PATH:-/tmp}"
TEST_COMPUTE="${TEST_COMPUTE:-true}"

# Report hostname
hostname

# GPU detection
echo "GPU_LIST_START"
nvidia-smi -L
echo "GPU_LIST_END"

echo "GPU_QUERY_START"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
echo "GPU_QUERY_END"

# Storage test
TESTFILE="${STORAGE_PATH}/.isvtest_node_$$"
if echo isvtest > "$TESTFILE" && cat "$TESTFILE" >/dev/null && rm -f "$TESTFILE"; then
    echo "STORAGE_OK"
else
    echo "STORAGE_FAILED: write/read/remove test failed at ${STORAGE_PATH}"
fi

# GPU compute test (optional)
if [ "$TEST_COMPUTE" = "true" ]; then
    echo "COMPUTE_START"

    if command -v nvcc >/dev/null 2>&1; then
        # Compile and run CUDA test
        CUDA_SRC="/tmp/gpu_test_$$.cu"
        CUDA_BIN="/tmp/gpu_test_$$"

        cat > "$CUDA_SRC" << 'CUDA_EOF'
{{GPU_COMPUTE_SOURCE}}
CUDA_EOF

        if nvcc -o "$CUDA_BIN" "$CUDA_SRC" -lcudart 2>/dev/null && "$CUDA_BIN"; then
            :  # Success - GPU_COMPUTE_OK printed by program
        else
            echo "GPU_COMPUTE_FAILED"
        fi
        rm -f "$CUDA_SRC" "$CUDA_BIN"

    elif command -v dcgmi >/dev/null 2>&1; then
        # Fallback: DCGM diagnostic
        if dcgmi diag -r 1 >/dev/null 2>&1; then
            echo "GPU_COMPUTE_OK"
        else
            echo "GPU_COMPUTE_FAILED"
        fi
    else
        echo "GPU_COMPUTE_SKIPPED"
    fi

    echo "COMPUTE_END"
fi
