# AGENTS.md

This file provides guidance to AI coding assistants when working with code in this repository.

## Project Overview

NVIDIA ISV NCP Validation Suite - Validation and management tools for NVIDIA ISV Lab GPU cluster environments. A monorepo containing three Python packages managed as a uv workspace:

- **isvctl** - Unified CLI controller for cluster lifecycle orchestration (setup -> test -> teardown)
- **isvtest** - Internal validation framework engine (pytest-based with custom discovery)
- **isvreporter** - Test results reporter for ISV Lab Service API

## Development Commands

### Package Management

```bash
# Install all packages and dependencies
uv sync
```

### Building

```bash
make build          # Build all packages (wheels output to dist/)
```

### Testing

```bash
make test           # Run tests for all packages
make smoke-test     # Run all 6 my-isv provider configs end-to-end in demo mode
                    # (sets ISVCTL_DEMO_MODE=1; no cloud needed; ~10s)
uv run pytest       # Run tests in current package directory

# isvtest has separate markers:
cd isvtest && uv run pytest -m unit              # Unit tests only
cd isvtest && uv run pytest -m validation        # Validation tests
cd isvtest && uv run pytest -m "not workload"    # Exclude long-running workload tests
```

### Linting and Formatting

```bash
make lint           # Run ruff linting on all packages
make format         # Format code with ruff
uvx pre-commit run -a                 # Run all pre-commit hooks
uvx ruff check src/                   # Lint specific package
uvx ruff format src/                  # Format specific package
```

### Cleaning

```bash
make clean          # Clean build artifacts and test outputs
```

### Running Tools

```bash
# isvctl - Main entry point for cluster validation
uv run isvctl test run -f isvctl/configs/tests/k8s.yaml
uv run isvctl test run -f isvctl/configs/tests/slurm.yaml -- -v -s -k "test_name"
uv run isvctl test run -f isvctl/configs/providers/aws/eks.yaml      # AWS EKS validation
uv run isvctl test run -f isvctl/configs/providers/aws/network.yaml  # AWS Network validation

# Remote deployment
uv run isvctl deploy run <target-ip> -f isvctl/configs/tests/k8s.yaml
uv run isvctl deploy run <target-ip> -j <jumphost> -u ubuntu -f config.yaml

# isvreporter - Upload test results to ISV Lab Service
uv run isvreporter --help
```

## Architecture

### Step-Based Execution Model

The framework uses a **step-based execution model** where:

1. **Scripts do the work** - External scripts (Python, Bash, etc.) perform cloud operations
2. **Scripts output JSON** - All operations output structured JSON to stdout
3. **Validations check JSON** - Simple assertions verify the JSON output

```text
Config (YAML) -> Script (any language) -> JSON output -> Validations (assertions)
```

**Lifecycle phases** run in order: `setup -> test -> teardown`. Key behaviors:

- **Teardown runs after failures** - If setup or test validations fail, teardown still executes so cloud resources are cleaned up
- **Best-effort teardown** - Individual teardown step failures don't block remaining teardown steps
- **Standalone teardown** - `isvctl test run -f config.yaml --phase teardown` runs cleanup independently (e.g., after a previous `AWS_SKIP_TEARDOWN` run)

**Benefits:**

- Language-agnostic: Scripts can be Python, Bash, Go, etc.
- Simple validations: Just check JSON fields, no cloud SDK code
- Reusable: Same script works across configs
- Debuggable: Run scripts manually, inspect JSON

### isvctl - Orchestration Layer

**Entry Point**: `isvctl/src/isvctl/main.py` - Typer-based CLI with subcommands

**Core Modules**:

- `cli/` - Subcommand implementations (test, deploy, clean, docs, report)
- `orchestrator/` - Lifecycle orchestration engine
  - `loop.py` - Main orchestration loop (setup -> test -> teardown phases); teardown runs even after earlier phase failures and uses best-effort execution
  - `step_executor.py` - Step execution and validation orchestration (delegates to pytest); supports `best_effort` mode for teardown
  - `commands.py` - Command execution with timeout handling
  - `context.py` - Jinja2 templating context for config variables and step outputs; warns when templates reference missing step data or fields (catches `ChainableUndefined` silent fallbacks)
- `config/` - Configuration schema and validation
  - `schema.py` - Pydantic models for config structure (including StepConfig)
  - `output_schemas.py` - JSON schema definitions for step outputs (auto-detection + validation)
  - `merger.py` - Config file merging logic (supports `-f file1.yaml -f file2.yaml`)
- `remote/` - Remote deployment functionality
  - `ssh.py` - SSH connection management with jumphost support
  - `archive.py` - Package tarball creation
  - `transfer.py` - SCP file transfer with jumphost proxy
- `cleaner/` - Resource cleanup operations

**Configuration Files**: Located in `isvctl/configs/tests/` (test definitions) and `isvctl/configs/providers/` (provider implementations)

- Configs define step-based commands with phases and validations
- Support Jinja2 templating: `"{{steps.create_network.vpc_id}}"`, `"{{region}}"` — the orchestrator warns when templates reference steps that haven't run or fields that don't exist, helping catch typos and rename mismatches
- Multiple configs can be merged with later files overriding earlier ones

**Stubs (ISV Scripts)**: Located in `isvctl/configs/stubs/`

- Platform setup/teardown shell scripts: `stubs/k8s/setup.sh`, `stubs/slurm/setup.sh`, etc.
- Provider-agnostic template stubs: `stubs/my-isv/<domain>/*.py` (iam, control-plane, vm, bare_metal, network, image-registry). Each stub has a TODO block and a `DEMO_MODE = os.environ.get("ISVCTL_DEMO_MODE") == "1"` gate: default run returns `"Not implemented - ..."` errors, `ISVCTL_DEMO_MODE=1` (what `make smoke-test` sets) returns dummy-success output. ISVs copy this tree as a starting point.
- AWS Python scripts organized by domain: `stubs/aws/network/`, `stubs/aws/vm/`, `stubs/aws/iam/`, etc. — fully implemented reference using boto3.
- Shared AWS utilities: `stubs/aws/common/` (error handling, EC2 helpers, VPC helpers)
- Shared stubs used by multiple domains: `stubs/common/` (SSH helpers, NIM deploy/teardown)
- Each script is self-contained and can be run manually for debugging

### isvtest - Validation Framework

**Entry Point**: `isvtest/src/isvtest/main.py` - Pytest integration layer

**Key Functions**:

- `run_validations_via_pytest()` - Bridge for isvctl to run validations via native pytest
  - Transforms validation configs to pytest-compatible format
  - Captures detailed results in-memory (no temp files)
  - Returns both exit code and rich result objects with categories/messages

**Core Modules**:

- `core/validation.py` - `BaseValidation` abstract class that all validation tests inherit from
- `core/discovery.py` - Dynamic test discovery (finds `BaseValidation` subclasses and ReFrame tests)
- `core/runners.py` - Command execution abstraction (`LocalRunner`, `SlurmRunner`, etc.)
- `core/k8s.py` - Kubernetes API utilities and helpers
- `core/slurm.py` - Slurm cluster interaction utilities
- `core/nvidia.py` - NVIDIA GPU detection and validation helpers
- `core/ngc.py` - NGC container registry utilities
- `core/workload.py` - Workload deployment and monitoring

**Validation Tests**: Located in `isvtest/src/isvtest/validations/`

Organized by category:

- `generic.py` - `StepSuccessCheck`, `FieldExistsCheck`, `FieldValueCheck`, `SchemaValidation`
- `cluster.py` - `ClusterHealthCheck`, `NodeCountCheck`, `GpuOperatorInstalledCheck`, `PerformanceCheck`
- `instance.py` - `InstanceStateCheck`, `InstanceCreatedCheck`, `InstanceRebootCheck`, `InstancePowerCycleCheck`, `StableIdentifierCheck`, etc.
- `network.py` - `NetworkProvisionedCheck`, `VpcCrudCheck`, `SubnetConfigCheck`, `SgCrudCheck`, `SecurityBlockingCheck`, etc.
- `iam.py` - `AccessKeyCreatedCheck`, `TenantCreatedCheck`, etc.
- `host.py` - Host-level validations (connectivity, OS, CPU, GPU, drivers, containers, cloud-init/metadata with optional `metadata_headers` for non-AWS providers)
- `ssh_helpers.py` - SSH connection and utility helpers (used by `host.py`)
- `k8s_*.py` - Kubernetes-specific validations (nodes, GPU operator, scheduling, MIG)
- `slurm_*.py` - Slurm-specific validations (partitions, jobs, GPU allocation)
- `bm_*.py` - Bare metal validations (CUDA, driver, GPU)

Each validation class:

- Inherits from `BaseValidation`
- Implements `run()` method that calls `self.set_passed()` or `self.set_failed()`
- Uses `markers: ClassVar[list[str]]` for filtering (e.g., `["kubernetes"]`, `["ssh", "gpu"]`)
- Is dynamically discovered by isvtest's discovery system

**Workloads**: Located in `isvtest/src/isvtest/workloads/`

- Long-running validation tests (NIM inference, NCCL benchmarks, stress tests)
- Includes Kubernetes manifests and helper scripts
- Use `markers: ClassVar[list[str]] = ["workload", "slow"]` for filtering
- Each workload class has detailed docstrings covering config options and troubleshooting

**Test Configuration**:

- Global fixtures in `isvtest/src/isvtest/tests/conftest.py`
- Custom pytest markers registered dynamically
- Config loaded via `config/loader.py` from YAML/JSON files
- `tests/test_validations.py` - Dynamically generates pytest tests from BaseValidation classes
  - Captures detailed results in-memory via module-level storage
  - Enables rich output (categories, messages) while using native pytest features

### isvreporter - Results Reporting

**Entry Point**: `isvreporter/src/isvreporter/main.py` - Typer-based CLI

**Core Modules**:

- `client.py` - ISV Lab Service API client
- `auth.py` - OAuth2 authentication handling
- `junit_parser.py` - Parse pytest JUnit XML output
- `platform.py` - Platform detection utilities

## Python Standards (from .cursor/rules/python-standards.mdc)

### Language & Types

- Python 3.12 required
- Use PEP 585 built-in collection types: `dict[str, Any]`, `list[int]`, `set[str]`
- DO NOT import from typing: `Dict`, `List`, `Set` (only import special types like `Any`, `Union`, `TypeVar`, `Protocol`)
- All functions and classes must have type annotations and docstrings (PEP 257)
- Explicit return types required for all functions

### Testing Standards

- Use pytest exclusively (no unittest)
- Tests must be in `tests/` directory with type annotations
- For isvtest: use `-m unit` for unit tests, `-m validation` for integration tests

### Configuration

- Use environment variables for configuration
- Implement robust error handling and logging

## Key Patterns

### Creating a New Validation Test

1. Create a new file in `isvtest/src/isvtest/validations/`
2. Inherit from `BaseValidation` and implement `run()` method
3. Set `markers: ClassVar[list[str]]` for filtering (e.g., `["kubernetes"]`)
4. Use `self.run_command()` to execute commands
5. Call `self.set_passed()` or `self.set_failed()` to set test result

Example:

```python
from isvtest.core.validation import BaseValidation
import pytest

class K8sMyCheck(BaseValidation):
    """Check something in Kubernetes."""

    description: ClassVar[str] = "Validates my Kubernetes component"
    timeout: ClassVar[int] = 60
    markers: ClassVar[list[str]] = ["kubernetes"]

    def run(self) -> None:
        result = self.run_command("kubectl get nodes")
        if result.returncode == 0:
            self.set_passed("Nodes found")
        else:
            self.set_failed("No nodes found", result.stderr)
```

### Creating a New Script (Step-Based)

Scripts perform cloud operations and output JSON:

```python
#!/usr/bin/env python3
"""Create VPC and output JSON."""

import argparse
import json
import sys
import boto3

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--region", default="us-west-2")
    args = parser.parse_args()

    result = {"success": False, "platform": "network"}

    try:
        ec2 = boto3.client("ec2", region_name=args.region)
        vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")
        result["network_id"] = vpc["Vpc"]["VpcId"]
        result["success"] = True
    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1

if __name__ == "__main__":
    sys.exit(main())
```

### Adding a Config with Steps

```yaml
version: "1.0"

commands:
  network:
    phases: ["setup", "test", "teardown"]
    steps:
      - name: create_network
        phase: setup
        command: "python ./stubs/aws/network/create_vpc.py"
        args: ["--name", "test-vpc", "--region", "{{region}}"]
        timeout: 300

      - name: teardown
        phase: teardown
        command: "python ./stubs/aws/network/teardown.py"
        args: ["--vpc-id", "{{steps.create_network.network_id}}"]

tests:
  platform: network
  cluster_name: "network-test"
  settings:
    region: "us-west-2"

  validations:
    network:
      - NetworkProvisionedCheck:
          step: create_network
      - StepSuccessCheck:
          step: teardown
```

### Remote Deployment Flow

1. `isvctl deploy run` packages repo into tarball (via `remote/archive.py`)
2. Transfers via SCP through optional jumphost (via `remote/transfer.py`)
3. Executes `install.sh` on remote target
4. Runs `isvctl test run` on remote with forwarded environment variables
5. Optionally uploads results via isvreporter

## Environment Variables

| Variable | Description | Used By |
| -------- | ----------- | ------- |
| `ISV_SERVICE_ENDPOINT` | ISV Lab Service API endpoint URL | isvreporter |
| `ISV_SSA_ISSUER` | ISV Lab Service SSA issuer URL | isvreporter |
| `ISV_CLIENT_ID` | ISV Lab Service client ID | isvreporter |
| `ISV_CLIENT_SECRET` | ISV Lab Service client secret | isvreporter |
| `NGC_API_KEY` | NGC API key for NIM workloads and container registry | isvtest, isvctl |
| `AWS_ACCESS_KEY_ID` | AWS access key | AWS scripts |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key | AWS scripts |
| `AWS_REGION` | AWS region | AWS scripts |
| `KUBECTL` | Optional kubectl-compatible CLI prefix (parsed with POSIX shlex in Python, word-split in shell stubs; overrides `K8S_PROVIDER` detection) | isvtest (`get_kubectl_command`), isvctl k8s stubs |

## Directory Structure Notes

- Workspace root `pyproject.toml` defines workspace members
- Each package has its own `pyproject.toml` with dependencies
- All source code in `src/` subdirectory per package
- Config files in `isvctl/configs/tests/` (test definitions) and `isvctl/configs/providers/` (provider implementations)
- ISV stubs (scripts) in `isvctl/configs/stubs/`
- Shared AWS utilities in `isvctl/configs/stubs/aws/common/`
- Schemas in `isvctl/schemas/` (JSON Schema files)
