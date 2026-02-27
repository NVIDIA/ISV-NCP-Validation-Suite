"""Kubernetes multi-node NCCL workload using MPI Operator.

Runs NCCL AllReduce tests across multiple nodes via MPIJob to verify
GPU-to-GPU communication over NVLink/NVSwitch (intra-node) and network
fabric (inter-node).

Requires the Kubeflow MPI Operator (kubeflow.org/v2beta1) to be installed
in the cluster.
"""

import subprocess
import time
import uuid
from pathlib import Path
from typing import ClassVar

from isvtest.config.settings import (
    get_k8s_namespace,
    get_nccl_hpc_image,
    get_nccl_min_bus_bw_gbps,
    get_nccl_multinode_gpus_per_node,
    get_nccl_multinode_nodes,
    get_nccl_multinode_timeout,
)
from isvtest.core.k8s import (
    get_gpu_nodes,
    get_kubectl_command,
    get_node_gpu_count,
    get_pod_logs,
    run_kubectl,
    wait_for_pod_completion,
)
from isvtest.core.workload import BaseWorkloadCheck
from isvtest.workloads.nccl_common import parse_nccl_output

_MPIJOB_LABEL_JOB_NAME = "training.kubeflow.org/job-name"
_MPIJOB_LABEL_REPLICA_TYPE = "training.kubeflow.org/replica-type"


class K8sNcclMultiNodeWorkload(BaseWorkloadCheck):
    """Run NCCL AllReduce test across multiple Kubernetes nodes via MPIJob.

    This workload validates GPU-to-GPU communication across multiple nodes
    using the NVIDIA HPC Benchmarks container orchestrated by the Kubeflow
    MPI Operator. It tests:
    - NVLink/NVSwitch bandwidth within nodes
    - Network fabric (InfiniBand/RoCE/RDMA) bandwidth between nodes
    - Data integrity (out-of-bounds check)

    Prerequisites:
        - Kubeflow MPI Operator installed (MPIJob CRD available)
        - At least 2 GPU nodes in the cluster
        - For full NVLink bandwidth across nodes: DRA driver with IMEX channels

    Config options:
        nodes (int): Number of nodes (default: 2 via env or auto-detect)
        gpus_per_node (int): GPUs per node (default: auto-detect, fallback 8)
        min_bus_bw_gbps (float): Minimum expected bus bandwidth in GB/s (default: 0 = no check)
        timeout (int): Job timeout in seconds (default: 900 via env)
        image (str): Container image (default: nvcr.io/nvidia/hpc-benchmarks:25.04)
    """

    description: ClassVar[str] = "Run NCCL AllReduce test across multiple K8s nodes (MPIJob)"
    timeout: ClassVar[int] = 1800
    markers: ClassVar[list[str]] = ["workload", "kubernetes", "gpu", "slow"]

    def run(self) -> None:
        """Execute multi-node NCCL test via MPIJob."""
        namespace = get_k8s_namespace()

        timeout_config = self.config.get("timeout")
        job_timeout = int(timeout_config) if timeout_config is not None else get_nccl_multinode_timeout()

        min_bus_bw_config = self.config.get("min_bus_bw_gbps")
        min_bus_bw = float(min_bus_bw_config) if min_bus_bw_config is not None else get_nccl_min_bus_bw_gbps()

        image = self.config.get("image") or get_nccl_hpc_image()

        if not self._check_mpi_operator():
            self.set_failed(
                "MPI Operator not found. Install the Kubeflow MPI Operator "
                "(https://github.com/kubeflow/mpi-operator) to run multi-node NCCL tests on K8s."
            )
            return

        gpu_nodes = get_gpu_nodes()
        if not gpu_nodes:
            self.set_passed("Skipped: No GPU nodes found in cluster")
            return

        if len(gpu_nodes) < 2:
            self.set_passed(f"Skipped: Multi-node NCCL test requires at least 2 GPU nodes, found {len(gpu_nodes)}")
            return

        node_count, gpus_per_node = self._resolve_topology(gpu_nodes)
        total_gpus = node_count * gpus_per_node
        job_name = f"nccl-allreduce-mn-{uuid.uuid4().hex[:8]}"

        self.log.info(
            f"Starting multi-node NCCL test: {node_count} nodes x {gpus_per_node} GPUs = {total_gpus} total GPUs"
        )
        self.log.info(f"Image: {image}, Min BW: {min_bus_bw} GB/s, Timeout: {job_timeout}s")

        manifest_path = Path(__file__).parent / "manifests" / "k8s" / "nccl_allreduce_mpijob.yaml"
        if not manifest_path.exists():
            self.set_failed(f"Manifest file not found: {manifest_path}")
            return

        yaml_content = manifest_path.read_text()
        yaml_content = self._patch_manifest(yaml_content, job_name, node_count, gpus_per_node, total_gpus, image)

        self.log.info(f"Deploying MPIJob {job_name} in namespace {namespace}...")
        try:
            result = subprocess.run(
                get_kubectl_command() + ["apply", "-f", "-", "-n", namespace],
                input=yaml_content,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                self.set_failed(f"Failed to create MPIJob: {result.stderr}")
                return
        except Exception as e:
            self.set_failed(f"Exception creating MPIJob: {e}")
            return

        try:
            self._wait_and_report(job_name, namespace, job_timeout, min_bus_bw, node_count, total_gpus)
        finally:
            self.log.info(f"Cleaning up MPIJob {job_name}...")
            run_kubectl(["delete", "mpijob", job_name, "-n", namespace, "--ignore-not-found=true"])

    def _check_mpi_operator(self) -> bool:
        """Check if the Kubeflow MPI Operator CRD is installed."""
        result = run_kubectl(["api-resources", "--api-group=kubeflow.org", "-o", "name"], timeout=10)
        if result.returncode != 0:
            return False
        return "mpijobs.kubeflow.org" in result.stdout

    def _resolve_topology(self, gpu_nodes: list[str]) -> tuple[int, int]:
        """Determine node count and GPUs per node from config or auto-detection.

        Returns:
            (node_count, gpus_per_node) tuple.
        """
        nodes_config = self.config.get("nodes")
        if nodes_config is not None:
            node_count = int(nodes_config)
        else:
            node_count = get_nccl_multinode_nodes()

        if len(gpu_nodes) < node_count:
            self.log.warning(
                f"Requested {node_count} nodes but only {len(gpu_nodes)} GPU nodes available, using {len(gpu_nodes)}"
            )
            node_count = len(gpu_nodes)

        gpus_config = self.config.get("gpus_per_node")
        if gpus_config is not None:
            gpus_per_node = int(gpus_config)
        else:
            detected = get_node_gpu_count(gpu_nodes[0])
            if detected > 0:
                gpus_per_node = detected
                self.log.info(f"Auto-detected {gpus_per_node} GPUs per node from {gpu_nodes[0]}")
            else:
                gpus_per_node = get_nccl_multinode_gpus_per_node()
                self.log.warning(f"Could not detect GPUs per node, using default: {gpus_per_node}")

        return node_count, gpus_per_node

    def _patch_manifest(
        self,
        yaml_content: str,
        job_name: str,
        node_count: int,
        gpus_per_node: int,
        total_gpus: int,
        image: str,
    ) -> str:
        """Replace placeholder values in the MPIJob manifest."""
        yaml_content = yaml_content.replace("name: nccl-allreduce-multinode", f"name: {job_name}", 1)
        yaml_content = yaml_content.replace("slotsPerWorker: 4", f"slotsPerWorker: {gpus_per_node}")
        yaml_content = yaml_content.replace("replicas: 2", f"replicas: {node_count}")
        yaml_content = yaml_content.replace("nvidia.com/gpu: 4", f"nvidia.com/gpu: {gpus_per_node}")
        yaml_content = yaml_content.replace("-np 8", f"-np {total_gpus}")
        if image != "nvcr.io/nvidia/hpc-benchmarks:25.04":
            yaml_content = yaml_content.replace("nvcr.io/nvidia/hpc-benchmarks:25.04", image)
        return yaml_content

    def _wait_and_report(
        self,
        job_name: str,
        namespace: str,
        timeout: int,
        min_bus_bw: float,
        node_count: int,
        total_gpus: int,
    ) -> None:
        """Wait for MPIJob launcher completion, collect logs, and report."""
        launcher_pod = self._wait_for_launcher_pod(job_name, namespace, timeout=120)
        if not launcher_pod:
            self.set_failed(f"Launcher pod for MPIJob {job_name} not found within 120s")
            return

        self.log.info(f"Launcher pod: {launcher_pod}, waiting for completion (timeout: {timeout}s)...")

        completed, phase = wait_for_pod_completion(launcher_pod, namespace, timeout=timeout)

        if not completed:
            self._dump_debug_info(job_name, namespace)
            self.set_failed(f"MPIJob {job_name} timed out after {timeout}s (launcher phase: {phase})")
            return

        logs = get_pod_logs(launcher_pod, namespace, container="launcher", timeout=60)

        if phase != "Succeeded":
            self.set_failed(f"MPIJob {job_name} failed (launcher phase: {phase})", output=logs)
            return

        self._check_and_report(logs, min_bus_bw, node_count, total_gpus, job_name)

    def _wait_for_launcher_pod(self, job_name: str, namespace: str, timeout: int = 120) -> str | None:
        """Wait for the MPIJob launcher pod to appear and return its name."""
        label_selector = f"{_MPIJOB_LABEL_JOB_NAME}={job_name},{_MPIJOB_LABEL_REPLICA_TYPE}=launcher"
        start = time.time()
        while time.time() - start < timeout:
            result = run_kubectl(
                [
                    "get",
                    "pods",
                    "-n",
                    namespace,
                    "-l",
                    label_selector,
                    "-o",
                    "jsonpath={.items[0].metadata.name}",
                ]
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
            time.sleep(5)
        return None

    def _dump_debug_info(self, job_name: str, namespace: str) -> None:
        """Log debug info on timeout to help troubleshoot."""
        label_selector = f"{_MPIJOB_LABEL_JOB_NAME}={job_name}"
        result = run_kubectl(["get", "pods", "-n", namespace, "-l", label_selector, "-o", "wide"])
        if result.returncode == 0:
            self.log.error(f"MPIJob pods:\n{result.stdout}")

        result = run_kubectl(["describe", "mpijob", job_name, "-n", namespace])
        if result.returncode == 0:
            self.log.error(f"MPIJob description:\n{result.stdout}")

    def _check_and_report(
        self,
        logs: str,
        min_bus_bw: float,
        node_count: int,
        total_gpus: int,
        job_name: str,
    ) -> None:
        """Parse NCCL output, check thresholds, and report results."""
        nccl = parse_nccl_output(logs)

        if not nccl.success:
            self.set_failed(nccl.error, output=nccl.output)
            return

        if min_bus_bw > 0 and nccl.avg_bus_bw_gbps < min_bus_bw:
            self.set_failed(
                f"Bus bandwidth {nccl.avg_bus_bw_gbps:.2f} GB/s below minimum threshold {min_bus_bw} GB/s",
                output=logs,
            )
            return

        oob_str = str(nccl.out_of_bounds) if nccl.out_of_bounds >= 0 else "N/A"
        msg = (
            f"NCCL multi-node test passed (MPIJob {job_name})\n"
            f"  Nodes: {node_count}\n"
            f"  Total GPUs: {total_gpus}\n"
            f"  Average Bus Bandwidth: {nccl.avg_bus_bw_gbps:.2f} GB/s\n"
            f"  Max Bus Bandwidth: {nccl.max_bus_bw_gbps:.2f} GB/s\n"
            f"  Out of Bounds: {oob_str}"
        )
        if min_bus_bw > 0:
            msg += f"\n  Minimum Required: {min_bus_bw} GB/s"

        self.set_passed(msg)
