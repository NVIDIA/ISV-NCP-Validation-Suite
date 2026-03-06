# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""InfiniBand availability check using ReFrame."""

from typing import ClassVar

import reframe as rfm
import reframe.utility.sanity as sn
from reframe.core.builtins import run_after, sanity_function


@rfm.simple_test
class InfiniBandCheck(rfm.RunOnlyRegressionTest):
    """Verify InfiniBand interfaces are available."""

    descr = "InfiniBand interface check"
    valid_systems: ClassVar[list[str]] = ["*"]
    valid_prog_environs: ClassVar[list[str]] = ["*"]
    executable = "ibstat"

    @run_after("init")
    def set_tags(self) -> None:
        """Set test tags."""
        self.tags = {"network", "infiniband"}

    @sanity_function
    def validate_ib(self) -> bool:
        """Check IB interface is active."""
        return sn.assert_found(r"State:\s+Active", self.stdout)
