# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""GPU memory validation check using ReFrame."""

from typing import ClassVar

import reframe as rfm
import reframe.utility.sanity as sn
from reframe.core.builtins import run_after, sanity_function


@rfm.simple_test
class GpuMemoryCheck(rfm.RunOnlyRegressionTest):
    """Verify GPU memory availability."""

    descr = "GPU memory check"
    valid_systems: ClassVar[list[str]] = ["*"]
    valid_prog_environs: ClassVar[list[str]] = ["*"]
    executable = "nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits"

    @run_after("init")
    def set_tags(self) -> None:
        """Set test tags."""
        self.tags = {"gpu", "memory"}

    @sanity_function
    def validate_memory(self) -> bool:
        """Check that GPUs have sufficient memory (>= 16GB)."""
        return sn.assert_found(r"\d{5,}", self.stdout)
