# ISV Test - NVIDIA ISV Lab Validation Framework

> **Note:** For cluster validation, use **`isvctl`** - the unified controller tool.
> `isvtest` is the internal validation engine used by `isvctl`.
>
> ```bash
> isvctl test run -f isvctl/configs/tests/k8s.yaml
> ```

A validation framework for NVIDIA ISV Lab environments supporting Kubernetes clusters, Slurm HPC systems, and bare metal servers.

## Quick Start

```bash
# Install
uv sync

# Use via isvctl (recommended)
isvctl test run -f isvctl/configs/tests/k8s.yaml
```

## Architecture

```text
isvtest/src/isvtest/
├── config/
│   ├── inventory.py     # Cluster inventory schema
│   ├── loader.py        # Config loader
│   └── settings.py      # Global settings
├── core/                # Framework core
│   ├── validation.py    # BaseValidation class
│   ├── workload.py      # BaseWorkloadCheck class
│   ├── runners.py       # Command runners
│   └── discovery.py     # Test discovery
├── validations/         # Quick validation tests
│   ├── bm_*.py          # Bare metal validations
│   ├── k8s_*.py         # Kubernetes validations
│   ├── slurm_*.py       # Slurm validations
│   └── reframe_*.py     # ReFrame validations
├── workloads/           # Workload-based tests (longer running)
│   ├── k8s_*.py         # K8s workloads (NCCL, stress, NIM)
│   ├── slurm_*.py       # Slurm workloads (NCCL, stress, sbatch)
│   └── reframe_*.py     # ReFrame tests
└── main.py              # CLI entry point
```

## Available Validations

### Bare Metal (`validations/bm_*.py`)

| Validation | Description |
| ---------- | ----------- |
| `BmDriverInstalled` | Verify NVIDIA driver is installed |
| `BmDriverVersion` | Check driver version meets minimum |
| `BmGpuDetection` | Detect GPUs and verify count |
| `BmGpuHealth` | Check GPU temperature and health |
| `BmGpuComputeCapability` | Verify compute capability |
| `BmCudaVersion` | Check CUDA version |

### Kubernetes (`validations/k8s_*.py`)

| Validation | Description |
| ---------- | ----------- |
| `K8sNodeCountCheck` | Verify node count |
| `K8sNodeReadyCheck` | Verify all nodes are Ready |
| `K8sNvidiaSmiCheck` | Run nvidia-smi on all GPU nodes |
| `K8sDriverVersionCheck` | Verify driver version across nodes |
| `K8sGpuPodAccessCheck` | Verify GPU access from pods (nvidia-smi) |
| `K8sGpuOperatorNamespaceCheck` | Verify GPU Operator namespace |
| `K8sGpuOperatorPodsCheck` | Verify GPU Operator pods running |
| `K8sPodHealthCheck` | Check pod health status |
| `K8sGpuLabelsCheck` | Verify GPU node labels |
| `K8sGpuCapacityCheck` | Verify node GPU capacity |
| `K8sMigConfigCheck` | Check MIG configuration |

### Slurm (`validations/slurm_*.py`)

| Validation | Description |
| ---------- | ----------- |
| `SlurmInfoAvailable` | Verify sinfo command works |
| `SlurmPartition` | Verify a Slurm partition exists and has expected nodes |
| `SlurmJobSubmission` | Test job submission |
| `SlurmGpuAllocation` | Test GPU allocation |

### Workloads (`workloads/`)

| Workload | Description |
| -------- | ----------- |
| `K8sNcclWorkload` | Single-node NCCL AllReduce validation |
| `K8sNcclMultiNodeWorkload` | Multi-node NCCL AllReduce via MPIJob |
| `K8sGpuStressWorkload` | GPU stress test |
| `K8sNimHelmWorkload` | NIM Helm deployment + GenAI-Perf KPIs |
| `K8sNimInferenceWorkload` | NIM inference validation |
| `SlurmNcclMultiNodeWorkload` | Multi-node NCCL AllReduce via Slurm |
| `SlurmGpuStressWorkload` | GPU stress test across Slurm partition |
| `SlurmSbatchWorkload` | Run arbitrary sbatch script |

Each workload class has detailed docstrings covering config options, environment variables, and troubleshooting.

#### Workload Prerequisites

Some workloads require additional cluster components beyond the base GPU Operator:

| Workload | Requirement | Notes |
| -------- | ----------- | ----- |
| `K8sNcclMultiNodeWorkload` | [Kubeflow MPI Operator](https://github.com/kubeflow/mpi-operator) | Provides the `MPIJob` CRD (`kubeflow.org/v2beta1`) used to orchestrate multi-node runs |
| `K8sNcclMultiNodeWorkload` | NVIDIA DRA driver (optional) | When the `ComputeDomain` CRD is present, MNNVL/IMEX channels are enabled automatically for full NVLink bandwidth across nodes. Controlled by `use_compute_domain: auto\|true\|false` |
| `K8sNimHelmWorkload` | `NGC_API_KEY` env var | Required to pull NIM models from NGC |

## Configuration Format

See [Configuration Guide](../guides/configuration.md) for full details.

The `tests:` section in isvctl configs uses this format (also used by legacy isvtest YAML):

```yaml
cluster_name: "MY_CLUSTER"
platform: kubernetes  # or slurm, bare_metal

validations:
  bare_metal:
    - BmDriverInstalled: {}
    - BmDriverVersion:
        min_version: "580.0"
    - BmGpuDetection:
        expected_count: 8

  kubernetes:
    - K8sNodeCountCheck:
        count: 3
    - K8sNodeReadyCheck: {}
    - K8sGpuOperatorPodsCheck:
        namespace: "gpu-operator"
    - K8sGpuPodAccessCheck:
        gpu_count: 1
    - K8sGpuCapacityCheck:
        expected_per_node: 8
        expected_total: 24

  slurm:
    - SlurmInfoAvailable: {}
    - SlurmPartition:
        partition_name: "gpu"

exclude:
  markers: [slow, workload]

settings:
  timeout: 60
  show_skipped_tests: true
```

## Test Markers

Filter tests using pytest markers:

- `bare_metal`, `kubernetes`, `slurm` - Platform-specific
- `gpu`, `network`, `hardware`, `software` - Component-specific
- `workload` - Workload-based tests (longer running)
- `slow` - Tests that take longer than 5 minutes
- `validation` - All validation tests (auto-applied)

**Note:** By default, `workload` and `slow` markers are excluded. Use `-k` to explicitly run them.

## Development

```bash
# Run unit tests
uv --directory=isvtest run pytest tests/ -v

# Lint
uvx pre-commit run -a
```

## Related Documentation

- [Local Development with MicroK8s](../guides/local-development.md) - Running K8s tests locally

## License

See [LICENSE](../../LICENSE) for license information.
