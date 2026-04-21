# isvctl - ISV Lab Controller

Controller tool for ISV Lab cluster lifecycle orchestration.

## Overview

`isvctl` is the unified tool for validating GPU clusters. It wraps around the
internal `isvtest` engine and provides:

1. **Setup**: Run inventory stubs that query or setup clusters
2. **Test**: Execute validation tests against the cluster
3. **Teardown**: Clean up resources (runs by default, even after test failures; see [teardown behavior](../guides/external-validation-guide.md#running-validations))

## Installation

```bash
# From workspace root
uv sync

# Verify installation
uv run isvctl --help
```

## Quick Start

```bash
# Validate a Kubernetes cluster
isvctl test run -f isvctl/configs/tests/k8s.yaml

# Validate a local MicroK8s
isvctl test run -f isvctl/configs/providers/microk8s.yaml

# Validate a local Minikube
isvctl test run -f isvctl/configs/providers/minikube.yaml

# Validate a local k3s
isvctl test run -f isvctl/configs/providers/k3s.yaml

# Validate a Slurm cluster
isvctl test run -f isvctl/configs/tests/slurm.yaml

# Pass extra pytest args
isvctl test run -f isvctl/configs/tests/k8s.yaml -- -v -s -k "NodeCount"
```

## Directory Structure

```text
isvctl/
├── configs/
│   ├── tests/         # Canonical test suites (vm.yaml, bare_metal.yaml, network.yaml, ...)
│   ├── providers/     # Provider configs (aws/, microk8s.yaml, minikube.yaml, k3s.yaml)
│   └── stubs/         # Lifecycle scripts (provider-agnostic templates + aws/ reference)
│       ├── vm/                # VM lifecycle stubs
│       ├── bare_metal/        # Bare metal lifecycle stubs
│       ├── network/           # Network validation stubs
│       ├── control-plane/     # API/IAM/tenant stubs
│       ├── iam/               # User lifecycle stubs
│       ├── image-registry/    # Image CRUD stubs
│       ├── common/            # Shared stubs (NIM deploy/teardown)
│       ├── k8s/               # Kubernetes setup/teardown
│       ├── slurm/             # Slurm setup/teardown
│       └── aws/               # AWS reference implementations
├── schemas/           # JSON Schema for validation
├── scripts/           # Helper scripts
├── src/               # isvctl Python source
└── tests/             # Unit tests
```

## Usage

### Run Validation

```bash
# Full lifecycle: setup (query inventory) -> test -> teardown
isvctl test run -f isvctl/configs/tests/k8s.yaml

# Run only the test phase (skip inventory query)
isvctl test run -f isvctl/configs/tests/k8s.yaml --phase test

# Run only teardown (cleanup from a previous run)
isvctl test run -f isvctl/configs/tests/k8s.yaml --phase teardown

# Dry run - validate config without executing
isvctl test run -f isvctl/configs/tests/k8s.yaml --dry-run

# Verbose with pytest options
isvctl test run -f isvctl/configs/tests/k8s.yaml -- -v -s --tb=short
```

### Merge Multiple Configs

```bash
# Base config + overrides
isvctl test run \
  -f base.yaml \
  -f overrides.yaml

# Override context values
isvctl test run -f config.yaml --set context.node_count=8
```

### Validate Configuration

```bash
# Check configuration syntax and schema
isvctl test validate -f isvctl/configs/tests/k8s.yaml
```

## Configuration Schema

See [Configuration Guide](../guides/configuration.md) for full details.

### Unified Config Structure

```yaml
version: "1.0"

commands:
  kubernetes:
    phases: ["setup", "test", "teardown"]
    steps:
      - name: setup
        phase: setup
        command: "../stubs/my-isv/k8s/setup.sh"  # replace "my-isv" with your ISV name
        timeout: 120
      - name: teardown
        phase: teardown
        command: "../stubs/my-isv/k8s/teardown.sh"  # replace "my-isv" with your ISV name
        timeout: 30

tests:
  platform: kubernetes
  cluster_name: "{{steps.setup.cluster_name}}"

  validations:
    kubernetes:
      checks:
        K8sNodeCountCheck:
          count: "{{steps.setup.kubernetes.node_count}}"
        K8sGpuCapacityCheck:
          expected_total: "{{steps.setup.kubernetes.total_gpus}}"
```

### Inventory Output Schema

Setup stubs must output JSON to stdout:

```json
{
  "platform": "kubernetes",
  "cluster_name": "my-cluster",
  "kubernetes": {
    "driver_version": "580.95.05",
    "node_count": 4,
    "nodes": ["node1", "node2", "node3", "node4"],
    "gpu_node_count": 4,
    "gpu_per_node": 4,
    "total_gpus": 16,
    "gpu_operator_namespace": "nvidia-gpu-operator",
    "runtime_class": "nvidia",
    "gpu_resource_name": "nvidia.com/gpu"
  }
}
```

This output is validated and becomes the `{{inventory.*}}` available in templates.

## Writing Custom Stubs

### Directory Organization

Place your provider-specific lifecycle scripts under `configs/stubs/<your-isv-name>/`, mirroring the structure of the `stubs/my-isv/` template scaffold (e.g. `configs/stubs/acme/k8s/setup.sh`). The stubs directory contains three trees:

- `stubs/my-isv/` - copy-and-fill-in template stubs for every domain
- `stubs/aws/` - fully-implemented AWS reference (follow its layout and JSON output contracts)
- `stubs/common/` - shared utilities used across providers

Stubs can be written in any language. They must:

1. Output valid JSON to stdout (for inventory/setup commands)
2. Exit with code 0 on success, non-zero on failure
3. Write logs/errors to stderr (not stdout)

### Example: Query Existing Cluster (Bash)

```bash
#!/bin/bash
# setup.sh - Query real cluster

kubectl get nodes -o json | jq '{
  platform: "kubernetes",
  cluster_name: "my-cluster",
  kubernetes: {
    node_count: (.items | length),
    nodes: [.items[].metadata.name],
    total_gpus: ([.items[].status.capacity."nvidia.com/gpu" // 0 | tonumber] | add)
  }
}'
```

### Example: Setup New Cluster (Python)

```python
#!/usr/bin/env python3
import json
import subprocess

# Setup cluster using ISV provisioning tool
result = subprocess.run(["isv-tool", "setup", "--nodes", "4"], capture_output=True)
cluster_id = result.stdout.strip()

# Output inventory JSON
print(json.dumps({
    "platform": "kubernetes",
    "cluster_name": cluster_id,
    "kubernetes": {
        "node_count": 4,
        "total_gpus": 16
    }
}))
```

## Remote Deployment

See [Remote Deployment Guide](../guides/remote-deployment.md) for full details.

```bash
# Deploy and run tests on remote machine
uv run isvctl deploy run 192.168.1.100 -u ubuntu -f isvctl/configs/tests/k8s.yaml

# With jumphost
uv run isvctl deploy run 192.168.1.100 -j jumphost.example.com -u ubuntu -f isvctl/configs/tests/k8s.yaml
```

## Development

```bash
# Run tests
uv --directory=isvctl run pytest

# Run linter
uvx pre-commit run -a

# Regenerate JSON schemas from Pydantic models
uv --directory=isvctl run python scripts/check_schemas.py --generate
```
