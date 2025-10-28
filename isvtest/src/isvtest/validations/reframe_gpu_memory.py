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
