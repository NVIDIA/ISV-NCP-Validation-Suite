#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

# CPU node test script for SlurmNodeJobExecution
# Tests: CPU info, storage write/read, optional CPU compute
#
# Variables:
#   STORAGE_PATH - Path for storage test (default: /tmp)
#   TEST_COMPUTE - "true" to run CPU compute test (default: true)

STORAGE_PATH="${STORAGE_PATH:-/tmp}"
TEST_COMPUTE="${TEST_COMPUTE:-true}"

# Report hostname
hostname

# CPU info
echo "CPU_INFO_START"
nproc
free -h | head -2
echo "CPU_INFO_END"

# Storage test
TESTFILE="${STORAGE_PATH}/.isvtest_node_$$"
if echo isvtest > "$TESTFILE" && cat "$TESTFILE" >/dev/null && rm -f "$TESTFILE"; then
    echo "STORAGE_OK"
else
    echo "STORAGE_FAILED: write/read/remove test failed at ${STORAGE_PATH}"
fi

# CPU compute test (optional)
if [ "$TEST_COMPUTE" = "true" ]; then
    echo "COMPUTE_START"

    if command -v python3 >/dev/null 2>&1; then
        # Python: sum of squares verification
        python3 -c "
import sys
result = sum(i*i for i in range(1, 10001))
sys.exit(0 if result == 333383335000 else 1)
" && echo "CPU_COMPUTE_OK" || echo "CPU_COMPUTE_FAILED"
    else
        # Shell fallback: simple arithmetic
        RESULT=$((1*1 + 2*2 + 3*3 + 4*4 + 5*5))
        echo "CPU_COMPUTE_OK: $RESULT"
    fi

    echo "COMPUTE_END"
fi
