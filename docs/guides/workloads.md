# Workloads

Workload-based validation tests for GPU clusters. These are longer-running tests that deploy real workloads to validate functionality.

## Quick Start

```bash
# Run all ReFrame workloads
uv run isvtest workload

# Run specific workload types
uv run isvtest workload --tags gpu
uv run isvtest workload --tags nccl
```

## Available Workloads

### GPU Stress (K8s)

**Class**: `K8sGpuStressWorkload`
**What**: PyTorch matrix multiplication under sustained load
**Platform**: Kubernetes

```yaml
validations:
  k8s_workloads:
    - K8sGpuStressWorkload:
        runtime: 30      # seconds
        memory_gb: 32     # GPU memory target
```

**Common Issues**:

- ARM64 nvrtc error: Set `GPU_CUDA_ARCH: "80"` (A100), `"90"` (H100), `"100"` (GB200)
- OOM error: Reduce `memory_gb` to match GPU size

### GPU Stress (Slurm)

**Class**: `SlurmGpuStressWorkload`
**What**: PyTorch matrix multiplication on all nodes in a Slurm partition
**Platform**: Slurm
**Container**: `nvcr.io/nvidia/pytorch:25.04-py3`

Runs GPU stress tests on **all nodes** in a partition simultaneously to verify each node can execute serious GPU workloads. Uses `srun` with labeled output to track per-node success/failure.

```yaml
validations:
  slurm_workloads:
    - SlurmGpuStressWorkload:
        partition: gpu           # Slurm partition to test
        runtime: 30              # seconds per node
        memory_gb: 32            # GPU memory target
        timeout: 420             # per-node timeout
        execution_mode: auto     # "container" | "python" | "auto"
        num_gpus: null           # null = Slurm default (typically 1)
        cuda_arch: null          # e.g., "100" for GB200
```

**Environment Variables**:

- `GPU_STRESS_IMAGE`: Container image (default: `nvcr.io/nvidia/pytorch:25.04-py3`)
- `GPU_STRESS_RUNTIME`: Runtime in seconds (default: 30)
- `GPU_STRESS_TIMEOUT`: Total timeout (default: 420)
- `GPU_MEMORY_GB`: GPU memory target in GB (default: 32)
- `GPU_CUDA_ARCH`: CUDA compute capability (e.g., "80", "90", "100")

**Common Issues**:

- Partition not GPU-enabled: Ensure partition has GRES gpu resources configured
- Container not available: Pre-pull image on compute nodes or use `execution_mode: python`
- Timeout: Increase `timeout` for slower nodes or larger memory allocations

### NCCL AllReduce (Single Node)

**Classes**: `NCCLAllReduceLocalTest`, `NCCLAllReduceTest`
**What**: Multi-GPU communication bandwidth test within a single node
**Platform**: Bare metal, Slurm, Kubernetes
**Container**: `nvcr.io/nvidia/hpc-benchmarks:25.04`

```yaml
validations:
  reframe:
    - NCCLAllReduceLocalTest:
        num_gpus: 8
```

**Metrics**: Average bus bandwidth (GB/s)

**Common Issues**:

- Container pull: Pre-pull with `singularity pull docker://nvcr.io/nvidia/hpc-benchmarks:25.04`
- Wrong GPU count: Adjust `num_gpus` in config

### NCCL AllReduce Multi-Node (Slurm)

**Class**: `SlurmNcclMultiNodeWorkload`
**What**: GPU-to-GPU communication test across multiple nodes
**Platform**: Slurm
**Container**: `nvcr.io/nvidia/hpc-benchmarks:25.04`

Runs NCCL AllReduce test across multiple Slurm nodes to validate:

- NVLink/NVSwitch bandwidth within nodes
- Network fabric (InfiniBand/RoCE) bandwidth between nodes
- Data integrity (out-of-bounds check)

```yaml
validations:
  slurm_workloads:
    - SlurmNcclMultiNodeWorkload:
        partition: gpu           # Slurm partition
        nodes: 2                 # Number of nodes
        # gpus_per_node: auto-detected from GRES
        min_bus_bw_gbps: 100     # Minimum expected bandwidth (0 = no check)
        timeout: 900             # Job timeout in seconds
        # container_runtime: docker (default), singularity, pyxis, or enroot
```

**Environment Variables**:

- `NCCL_HPC_IMAGE`: Container image (default: `nvcr.io/nvidia/hpc-benchmarks:25.04`)
- `NCCL_MULTINODE_NODES`: Number of nodes (default: 2)
- `NCCL_MULTINODE_GPUS_PER_NODE`: GPUs per node (default: 8)
- `NCCL_MULTINODE_TIMEOUT`: Timeout in seconds (default: 900)
- `NCCL_MIN_BUS_BW_GBPS`: Minimum bus bandwidth threshold (default: 0)

**Metrics**:

- Average bus bandwidth (GB/s)
- Max bus bandwidth (GB/s)
- Out of bounds values (data corruption check)

**Common Issues**:

- Insufficient nodes: Requires at least 2 nodes in partition
- Container runtime: Ensure Pyxis/Enroot/Singularity is configured on compute nodes
- Network fabric: Low bandwidth may indicate misconfigured InfiniBand/RoCE
- Timeout: Increase for larger node counts or slower networks

### NIM Helm Deployment (K8s)

**Class**: `K8sNimHelmWorkload`
**Requires**: Helm, `NGC_NIM_API_KEY` env var, GPU node

Deploys NIM via Helm, validates inference, runs GenAI-Perf for performance metrics.

```yaml
validations:
  k8s_workloads:
    - K8sNimHelmWorkload:
        model: "meta/llama-3.2-3b-instruct"
        gpu_count: 1                          # Use 4 for tensor parallelism
        genai_perf_requests: 100
        genai_perf_concurrency: 1
        # Dev options (faster iteration):
        # skip_cleanup: true                  # Keep NIM running after test
        # reuse_deployment: "nim-bench-xxx"   # Skip deploy, use existing
```

**Metrics**: Request throughput, token throughput, TTFT, ITL, request latency (avg/p99)

**Output**: GenAI-Perf artifacts saved to `_output/genai-perf/`

**Notes**:

- First run: ~15 min (model download + TensorRT compilation)
- Subsequent runs with `reuse_deployment`: ~1 min
- Multi-GPU: Set `gpu_count: 4` for tensor parallelism (requires NVLink)

## Configuration

Add workloads to your cluster YAML under `validations.k8s_workloads` or `validations.reframe` (ReFrame).

See [Configuration Guide](configuration.md) for full details on config file format.
