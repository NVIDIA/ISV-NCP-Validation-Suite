# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""CPU information validation check using ReFrame."""

from typing import Any, ClassVar

import reframe as rfm
import reframe.utility.sanity as sn
from reframe.core.builtins import performance_function, run_after, sanity_function


@rfm.simple_test
class CPUInfoCheck(rfm.RunOnlyRegressionTest):
    """Verify CPU information is available and readable."""

    descr = "CPU information check using lscpu"
    valid_systems: ClassVar[list[str]] = ["*"]
    valid_prog_environs: ClassVar[list[str]] = ["*"]
    executable = "/usr/bin/lscpu"

    @run_after("init")
    def set_tags(self) -> None:
        """Set test tags."""
        self.tags = {"system", "cpu", "basic"}

    @sanity_function
    def validate(self) -> Any:
        """Check that Architecture information is present in output."""
        return sn.assert_found(r"Architecture", self.stdout)

    @performance_function("CPU(s)")
    def cpu_nums(self) -> Any:
        """Extract number of CPUs from lscpu output.

        Returns:
            Number of CPUs reported by the system.
        """
        return sn.extractsingle(r"^CPU\(s\):\s+(\d+)", self.stdout, 1, int)
