"""NCCL AllReduce performance test using HPC benchmarks container.

This test uses the NVIDIA HPC Benchmarks container from NGC:
https://catalog.ngc.nvidia.com/orgs/nvidia/containers/hpc-benchmarks?version=25.04

The container includes:
- NVIDIA HPL 25.09
- NVIDIA HPL-MxP 25.09
- NVIDIA HPCG 25.09
- NVIDIA STREAM 25.09
- NVIDIA NVSHMEM 3.4.5
- NVIDIA NVPL 25.1

Note: This test requires:
- Slurm with container support (Enroot/Singularity/Pyxis), OR
- Local container runtime (Singularity, Docker, or Enroot with GPU support)
"""

from typing import Any, ClassVar

import reframe as rfm
import reframe.core.builtins as rfm_builtins
import reframe.utility.sanity as rfm_sanity


@rfm.simple_test
class NCCLAllReduceTest(rfm.RunOnlyRegressionTest):
    """NCCL AllReduce test using container-based execution."""

    descr = "NCCL AllReduce performance test with HPC benchmarks container"
    valid_systems: ClassVar[list[str]] = ["*"]
    valid_prog_environs: ClassVar[list[str]] = ["*"]

    # Use ReFrame's container platform for cleaner integration
    container_platform = "Singularity"

    # Configurable GPU count for different node topologies
    num_gpus = rfm_builtins.variable(int, value=4)

    @rfm_builtins.run_after("init")
    def set_tags(self) -> None:
        """Set test tags."""
        self.tags = {"nccl", "workload", "hpc", "network", "performance"}

    @rfm_builtins.run_before("run")
    def set_container_image(self) -> None:
        """Configure container image for NCCL tests using ReFrame's native container support."""
        # ReFrame converts container_platform string to object before this hook
        self.container_platform.image = "nvcr.io/nvidia/hpc-benchmarks:25.04"  # type: ignore[attr-defined]
        self.container_platform.command = "all_reduce_perf"  # type: ignore[attr-defined]

    @rfm_builtins.run_before("run")
    def set_nccl_parameters(self) -> None:
        """Set NCCL-specific parameters for AllReduce test.

        Parameters:
            -b 8: Start size at 8 bytes
            -e 4G: End size at 4 GB
            -f 2: Size multiplication factor of 2
            -g <num_gpus>: Number of GPUs to use (configurable)
        """
        self.executable_opts = ["-b", "8", "-e", "4G", "-f", "2", "-g", str(self.num_gpus)]

    @rfm_builtins.sanity_function
    def assert_nccl_success(self) -> Any:
        """Verify NCCL test completed successfully."""
        return rfm_sanity.assert_ge(self.avg_bus_bandwidth(), 0)

    @rfm_builtins.performance_function("GB/s")
    def avg_bus_bandwidth(self) -> Any:
        """Extract average bus bandwidth performance metric.

        Returns:
            Average bus bandwidth in GB/s.
        """
        pattern = r"# Avg bus bandwidth\s*:\s*([\d.]+)"
        return rfm_sanity.extractsingle(pattern, self.stdout, 1, float)
