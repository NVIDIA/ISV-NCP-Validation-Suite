"""Slurm multi-node NCCL workload.

This module runs NCCL AllReduce tests across multiple nodes to verify
GPU-to-GPU communication over NVLink/NVSwitch (intra-node) and network
fabric (inter-node).

This ensures that serious computation jobs can be run across multiple nodes
and benefit from NVLink/NVSwitch to accelerate those jobs.
"""

import os
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from isvtest.config.settings import (
    get_nccl_hpc_image,
    get_nccl_min_bus_bw_gbps,
    get_nccl_multinode_gpus_per_node,
    get_nccl_multinode_nodes,
    get_nccl_multinode_timeout,
)
from isvtest.core.slurm import (
    TERMINAL_STATES,
    get_job_output,
    get_job_state,
    get_partition_gpus_per_node,
    get_partition_nodes,
    is_gpu_partition,
    parse_sbatch_job_id,
)
from isvtest.core.workload import BaseWorkloadCheck

MANIFESTS_DIR = Path(__file__).parent / "manifests" / "slurm"


@dataclass
class NcclResult:
    """Result of NCCL multi-node test."""

    success: bool
    job_id: str = ""
    avg_bus_bw_gbps: float = 0.0
    max_bus_bw_gbps: float = 0.0
    out_of_bounds: int = 0
    nodes_used: int = 0
    total_gpus: int = 0
    error: str = ""
    output: str = ""


class SlurmNcclMultiNodeWorkload(BaseWorkloadCheck):
    """Run NCCL AllReduce test across multiple Slurm nodes.

    This workload validates GPU-to-GPU communication across multiple nodes
    using the NVIDIA HPC Benchmarks container. It tests:
    - NVLink/NVSwitch bandwidth within nodes
    - Network fabric (InfiniBand/RoCE) bandwidth between nodes
    - Data integrity (out-of-bounds check)

    Config options:
        partition (str): Slurm partition to use (default: "gpu")
        nodes (int): Number of nodes to test (default: 2 via env or auto-detect)
        gpus_per_node (int): GPUs per node (default: auto-detect from GRES, fallback 8)
        min_bus_bw_gbps (float): Minimum expected bus bandwidth in GB/s (default: 0 = no check)
        timeout (int): Job timeout in seconds (default: 900 via env)
        image (str): Container image (default: nvcr.io/nvidia/hpc-benchmarks:25.04)
        container_runtime (str): "docker" | "singularity" | "pyxis" | "enroot" (default: "docker")
        quick_mode (bool): Use reduced message sizes for faster execution (default: True)
            - True: 1M-256M range, ~30 seconds (CI/dev validation)
            - False: 8B-4G range, 2-5 minutes (full performance test)
    """

    description: ClassVar[str] = "Run NCCL AllReduce test across multiple Slurm nodes"
    timeout: ClassVar[int] = 1800
    markers: ClassVar[list[str]] = ["workload", "slurm", "gpu", "slow"]

    def run(self) -> None:
        """Execute multi-node NCCL test."""
        partition = self.config.get("partition", "gpu")
        nodes_config = self.config.get("nodes")
        gpus_config = self.config.get("gpus_per_node")

        min_bus_bw_config = self.config.get("min_bus_bw_gbps")
        min_bus_bw = float(min_bus_bw_config) if min_bus_bw_config is not None else get_nccl_min_bus_bw_gbps()

        timeout_config = self.config.get("timeout")
        job_timeout = int(timeout_config) if timeout_config is not None else get_nccl_multinode_timeout()

        image = self.config.get("image") or get_nccl_hpc_image()
        container_runtime = self.config.get("container_runtime", "docker")
        quick_mode = self.config.get("quick_mode", True)

        # Validate partition is GPU-enabled
        if not is_gpu_partition(self, partition):
            self.set_failed(f"Partition '{partition}' is not a GPU partition")
            return

        # Get available nodes and validate we have enough
        available_nodes = get_partition_nodes(self, partition)
        if available_nodes is None:
            return  # Error already set

        # Determine node count
        nodes = int(nodes_config) if nodes_config is not None else get_nccl_multinode_nodes()
        if len(available_nodes) < nodes:
            if len(available_nodes) < 2:
                self.set_failed(
                    f"Multi-node NCCL test requires at least 2 nodes, "
                    f"partition '{partition}' has {len(available_nodes)}"
                )
                return
            # Use what we have
            self.log.warning(
                f"Requested {nodes} nodes but only {len(available_nodes)} available, using {len(available_nodes)}"
            )
            nodes = len(available_nodes)

        # Determine GPUs per node - auto-detect from partition if not specified
        if gpus_config is not None:
            gpus_per_node = int(gpus_config)
        else:
            detected_gpus = get_partition_gpus_per_node(self, partition)
            if detected_gpus:
                gpus_per_node = detected_gpus
                self.log.info(f"Auto-detected {gpus_per_node} GPUs per node from partition GRES")
            else:
                gpus_per_node = get_nccl_multinode_gpus_per_node()
                self.log.warning(f"Could not detect GPUs per node, using default: {gpus_per_node}")

        total_gpus = nodes * gpus_per_node
        mode_str = "quick" if quick_mode else "full"
        self.log.info(
            f"Starting NCCL test ({mode_str} mode): {nodes} nodes x {gpus_per_node} GPUs = {total_gpus} total GPUs"
        )
        if container_runtime == "docker":
            self.log.info("Docker mode: Running intra-node multi-GPU NCCL test on each node")
        else:
            self.log.info(f"{container_runtime} mode: True multi-node NCCL test")
        self.log.info(f"Image: {image}, Min BW: {min_bus_bw} GB/s, Timeout: {job_timeout}s")

        # Generate and submit the job
        script = self._generate_sbatch_script(
            partition=partition,
            nodes=nodes,
            gpus_per_node=gpus_per_node,
            image=image,
            container_runtime=container_runtime,
            quick_mode=quick_mode,
        )

        result = self._submit_and_wait(script, job_timeout)

        # Report results
        self._report_result(result, min_bus_bw, nodes, total_gpus)

    def _load_template(self, template_name: str, variables: dict[str, str | int]) -> str:
        """Load a template file and substitute variables.

        Args:
            template_name: Name of the template file in manifests/slurm/
            variables: Dictionary of variable names to values for substitution

        Returns:
            The template with {{VARIABLE}} placeholders replaced
        """
        template_path = MANIFESTS_DIR / template_name
        template = template_path.read_text()

        for key, value in variables.items():
            template = template.replace(f"{{{{{key}}}}}", str(value))

        return template

    def _generate_sbatch_script(
        self,
        partition: str,
        nodes: int,
        gpus_per_node: int,
        image: str,
        container_runtime: str,
        quick_mode: bool = True,
    ) -> str:
        """Generate sbatch script for multi-node NCCL test."""
        total_gpus = nodes * gpus_per_node
        job_name = f"isvtest-nccl-{os.getpid()}"

        # NCCL test parameters based on mode
        if quick_mode:
            nccl_size_params = "-b 1M -e 256M -f 2"
        else:
            nccl_size_params = "-b 8 -e 4G -f 2"

        # For Docker: Run one container per node with all GPUs
        if container_runtime == "docker":
            return self._load_template(
                "nccl_allreduce_docker.sh",
                {
                    "JOB_NAME": job_name,
                    "PARTITION": partition,
                    "NODES": nodes,
                    "GPUS_PER_NODE": gpus_per_node,
                    "TOTAL_GPUS": total_gpus,
                    "IMAGE": image,
                    "NCCL_SIZE_PARAMS": nccl_size_params,
                },
            )

        # For Pyxis/Enroot/Singularity: True multi-node with one task per GPU
        total_tasks = nodes * gpus_per_node
        nccl_params = f"{nccl_size_params} -g 1"

        if container_runtime == "pyxis":
            container_opts = f"--container-image={image}"
            nccl_cmd = f"all_reduce_perf {nccl_params}"
        elif container_runtime == "enroot":
            container_opts = f"--container-image={image}"
            nccl_cmd = f"all_reduce_perf {nccl_params}"
        else:  # singularity
            container_opts = ""
            nccl_cmd = f"singularity exec --nv docker://{image} all_reduce_perf {nccl_params}"

        return self._load_template(
            "nccl_allreduce_mpi.sh",
            {
                "JOB_NAME": job_name,
                "PARTITION": partition,
                "NODES": nodes,
                "TOTAL_TASKS": total_tasks,
                "GPUS_PER_NODE": gpus_per_node,
                "IMAGE": image,
                "CONTAINER_RUNTIME": container_runtime,
                "CONTAINER_OPTS": container_opts,
                "NCCL_CMD": nccl_cmd,
            },
        )

    def _submit_and_wait(self, script: str, timeout: int) -> NcclResult:
        """Submit sbatch script and wait for completion."""
        # Write script to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False, prefix="isvtest_nccl_") as f:
            f.write(script)
            script_path = f.name

        self.log.debug(f"Wrote NCCL script to: {script_path}")

        try:
            # Submit job
            submit_result = self.run_command(f"sbatch {script_path}", timeout=30)

            if submit_result.exit_code != 0:
                return NcclResult(
                    success=False,
                    error=f"sbatch failed (exit {submit_result.exit_code}): {submit_result.stderr}",
                )

            job_id = parse_sbatch_job_id(submit_result.stdout)
            if not job_id:
                return NcclResult(
                    success=False,
                    error=f"Could not parse job ID from: {submit_result.stdout}",
                )

            self.log.info(f"Submitted NCCL job {job_id}")
            return self._wait_for_job(job_id, timeout)

        finally:
            # Cleanup temp script
            try:
                os.unlink(script_path)
            except OSError:
                pass

    def _wait_for_job(self, job_id: str, timeout: int) -> NcclResult:
        """Wait for job completion and collect results."""
        start_time = time.time()
        end_time = start_time + timeout
        poll_interval = 10
        use_sacct = True
        nodelist = ""

        while time.time() < end_time:
            state, exit_code, node_info, sacct_ok = get_job_state(self, job_id, use_sacct)
            use_sacct = sacct_ok
            if node_info:
                nodelist = node_info

            self.log.debug(f"Job {job_id} state: {state}")

            if state in TERMINAL_STATES:
                duration = time.time() - start_time
                self.log.info(f"Job {job_id} completed: state={state}, duration={duration:.1f}s")

                # Get job output
                stdout, stderr = get_job_output(self, job_id, nodelist, cleanup=True)
                output = f"{stdout}\n{stderr}".strip()

                if state != "COMPLETED" or exit_code != 0:
                    return NcclResult(
                        success=False,
                        job_id=job_id,
                        error=f"Job {state} with exit code {exit_code}",
                        output=output,
                    )

                # Parse NCCL results
                return self._parse_nccl_output(job_id, output)

            time.sleep(poll_interval)

        # Timeout - cancel the job
        self.log.warning(f"Job {job_id} timed out after {timeout}s, cancelling...")
        self.run_command(f"scancel {job_id}", timeout=30)

        return NcclResult(
            success=False,
            job_id=job_id,
            error=f"Job timed out after {timeout}s",
        )

    def _parse_nccl_output(self, job_id: str, output: str) -> NcclResult:
        """Parse NCCL test output for bandwidth and errors."""
        result = NcclResult(success=True, job_id=job_id, output=output)

        # Extract average bus bandwidth
        # Format: "# Avg bus bandwidth    : 123.45"
        avg_bw_match = re.search(r"#\s*Avg bus bandwidth\s*:\s*([\d.]+)", output)
        if avg_bw_match:
            result.avg_bus_bw_gbps = float(avg_bw_match.group(1))
            self.log.info(f"Average Bus Bandwidth: {result.avg_bus_bw_gbps:.2f} GB/s")

        # Extract max bus bandwidth (from the data table, last non-empty algbw value)
        # Look for lines like: "  4294967296    1073741824    float     sum    123.45    456.78"
        bw_matches = re.findall(r"^\s+\d+\s+\d+\s+\w+\s+\w+\s+[\d.]+\s+([\d.]+)", output, re.MULTILINE)
        if bw_matches:
            result.max_bus_bw_gbps = max(float(bw) for bw in bw_matches)
            self.log.info(f"Max Bus Bandwidth: {result.max_bus_bw_gbps:.2f} GB/s")

        # Check for out of bounds errors (data corruption)
        # Format: "# Out of bounds values : 0 OK"
        oob_match = re.search(r"#\s*Out of bounds values\s*:\s*(\d+)", output)
        if oob_match:
            result.out_of_bounds = int(oob_match.group(1))
            if result.out_of_bounds > 0:
                result.success = False
                result.error = f"Data corruption detected: {result.out_of_bounds} out of bounds values"
                self.log.error(result.error)

        # Extract node count from output
        nodes_match = re.search(r"Nodes:\s*(\d+)", output)
        if nodes_match:
            result.nodes_used = int(nodes_match.group(1))

        gpus_match = re.search(r"Total GPUs:\s*(\d+)", output)
        if gpus_match:
            result.total_gpus = int(gpus_match.group(1))

        # Validate we got bandwidth results
        if result.avg_bus_bw_gbps == 0 and result.max_bus_bw_gbps == 0:
            result.success = False
            result.error = "Could not parse bandwidth results from NCCL output"
            self.log.warning(f"NCCL output parsing failed. Raw output:\n{output[:2000]}")

        return result

    def _report_result(self, result: NcclResult, min_bus_bw: float, nodes: int, total_gpus: int) -> None:
        """Report test results."""
        if not result.success:
            msg = "NCCL multi-node test failed"
            if result.job_id:
                msg += f" (job {result.job_id})"
            if result.error:
                msg += f": {result.error}"
            self.set_failed(msg, output=result.output)
            return

        # Check minimum bandwidth threshold
        if min_bus_bw > 0 and result.avg_bus_bw_gbps < min_bus_bw:
            self.set_failed(
                f"Bus bandwidth {result.avg_bus_bw_gbps:.2f} GB/s below minimum threshold {min_bus_bw} GB/s",
                output=result.output,
            )
            return

        # Success
        msg = (
            f"NCCL multi-node test passed (job {result.job_id})\n"
            f"  Nodes: {result.nodes_used or nodes}\n"
            f"  Total GPUs: {result.total_gpus or total_gpus}\n"
            f"  Average Bus Bandwidth: {result.avg_bus_bw_gbps:.2f} GB/s\n"
            f"  Max Bus Bandwidth: {result.max_bus_bw_gbps:.2f} GB/s\n"
            f"  Out of Bounds: {result.out_of_bounds} (OK)"
        )
        if min_bus_bw > 0:
            msg += f"\n  Minimum Required: {min_bus_bw} GB/s ✓"

        self.set_passed(msg)
