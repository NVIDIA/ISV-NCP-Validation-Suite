# Configuration Guide

This guide covers the configuration file format and options for ISV NCP Validation Suite.

## Overview

Configuration files define what tests to run and how to run them. They use YAML format with:

- **Step-based execution** - Scripts perform operations and output JSON
- **Schema validation** - Output is validated against auto-detected or explicit schemas
- **Advanced validations** - Field checks, state verification, cross-step comparisons
- **Phase ordering** - Define custom phases that execute in order
- **Centralized validations** - All validations in `tests.validations` section
- **Template variables** - Reference step outputs and settings via Jinja2

## Architecture

```text
┌──────────────────────────────────────────────────────────────────┐
│                     Step-Based Execution                         │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Config (YAML)          Scripts (Any Language)    Validations    │
│  ┌──────────────┐      ┌──────────────────┐     ┌────────────┐   │
│  │ phases: [...]│      │ provision.py     │     │ Check JSON │   │
│  │ steps:       │─────▶│ create_vpc.py    │────▶│ output for │   │
│  │   - name: x  │      │ launch_vm.sh     │     │ success    │   │
│  │     phase    │      │ check_api.py     │     │            │   │
│  │     command  │      └──────────────────┘     └────────────┘   │
│  └──────────────┘              │                      │          │
│                                │                      │          │
│                                ▼                      ▼          │
│                         JSON Output              Pass/Fail       │
│                         {"success": true,        assertions      │
│                          "vpc_id": "vpc-xxx"}                    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**Benefits:**

- **Language-agnostic** - Scripts can be Python, Bash, Go, etc.
- **Simple validations** - Just check JSON output fields
- **Reusable scripts** - Same script works across configs
- **Easy debugging** - Run scripts manually, inspect JSON

## Example Configs

Pre-built configs are provided in `isvctl/configs/`:

| Config | Description |
| ------ | ----------- |
| `aws/control-plane.yaml` | AWS API health, access key lifecycle, tenant management |
| `aws/network.yaml` | AWS VPC network validation (6 test suites) |
| `aws/vm.yaml` | AWS EC2 GPU instance tests |
| `aws/iam.yaml` | AWS IAM user lifecycle |
| `aws/eks.yaml` | AWS EKS with GPU nodes |
| `k8s.yaml` | Standard Kubernetes cluster |
| `slurm.yaml` | Slurm HPC cluster |

## Basic Usage

```bash
# Run a config
isvctl test run -f isvctl/configs/aws/control-plane.yaml

# Merge multiple configs (later files override earlier ones)
isvctl test run -f isvctl/configs/aws/eks.yaml -f my-overrides.yaml

# Verbose output (shows script output on failure)
isvctl test run -f config.yaml -v

# Validate config without running
isvctl test run -f config.yaml --dry-run

# Pass pytest arguments after --
isvctl test run -f config.yaml -- -v -s -k "NodeCount"
```

## Config Structure

### Complete Example

```yaml
version: "1.0"

commands:
  network:
    # Phases execute in this order
    phases: ["setup", "test", "teardown"]

    steps:
      # Step 1: Create VPC (setup phase)
      - name: create_network
        phase: setup
        command: "python ./scripts/create_vpc.py"
        args:
          - "--name"
          - "test-vpc"
          - "--region"
          - "{{region}}"
        timeout: 300

      # Step 2: Run tests (test phase)
      - name: test_connectivity
        phase: test
        command: "python ./scripts/test_connectivity.py"
        args:
          - "--vpc-id"
          - "{{steps.create_network.network_id}}"
        timeout: 600

      # Step 3: Cleanup (teardown phase)
      - name: teardown
        phase: teardown
        command: "python ./scripts/teardown.py"
        args:
          - "--vpc-id"
          - "{{steps.create_network.network_id}}"
        timeout: 300

tests:
  platform: network
  cluster_name: "aws-network-test"

  settings:
    region: "us-west-2"

  # Centralized validations grouped by category
  validations:
    network:
      - NetworkProvisionedCheck:
          step: create_network
      - StepSuccessCheck:
          step: test_connectivity
          check_success: true

    teardown_checks:
      - StepSuccessCheck:
          step: teardown
```

### Platform Configuration

Each platform defines phases and steps:

```yaml
commands:
  network:
    phases: ["setup", "test", "teardown"]    # Execution order
    steps: [...]                              # Steps grouped by phase
```

| Field | Required | Description |
| ----- | -------- | ----------- |
| `phases` | No | Ordered list of phases (default: `["setup", "test", "teardown"]`) |
| `steps` | Yes | List of step configurations |
| `skip` | No | Skip this entire platform |

**Important:** If a step's `phase` is not in the `phases` list, an error is raised.

### Step Configuration

Each step defines a command to execute:

```yaml
- name: create_network
  phase: setup
  command: "python ./scripts/create_vpc.py"
  args: ["--region", "{{region}}"]
  timeout: 300
  env:
    AWS_PROFILE: "production"
  skip: false
  continue_on_failure: false
  output_schema: vpc
```

| Field | Required | Description |
| ----- | -------- | ----------- |
| `name` | Yes | Unique step identifier (used for output references) |
| `phase` | No | Phase this step belongs to (default: `setup`) |
| `command` | Yes | Script/command to execute |
| `args` | No | Arguments (supports Jinja2 templates) |
| `timeout` | No | Timeout in seconds (default: 300) |
| `env` | No | Environment variables |
| `skip` | No | Skip this step |
| `continue_on_failure` | No | Continue even if this step fails |
| `output_schema` | No | Schema name for output validation |

### Validation Configuration

Validations are centralized in `tests.validations`, grouped by category:

```yaml
tests:
  validations:
    # Category name (any meaningful name)
    network:
      - NetworkProvisionedCheck:
          step: create_network

    # Validations can specify when to run
    teardown_checks:
      - StepSuccessCheck:
          step: teardown
```

**Validation Timing (`phase`):**

| Value | When it runs |
| ----- | ------------ |
| *(not set)* | After setup phase (default) |
| `teardown` | After teardown phase |
| `<phase>` | After the specified phase |

### Test Variants

A validation check can be run multiple times with different parameters by appending a **dash-separated suffix** to the class name. The dash (`-`) is the only accepted variant separator.

```yaml
validations:
  k8s_workloads:
    checks:
      - K8sNimHelmWorkload-1b:
          model: "meta/llama-3.2-1b-instruct"
          gpu_count: 1
          timeout: 900
      - K8sNimHelmWorkload-3b:
          model: "meta/llama-3.2-3b-instruct"
          gpu_count: 4
          timeout: 1800

  slurm:
    checks:
      - SlurmPartition-cpu:
          partition_name: "cpu"
      - SlurmPartition-gpu:
          partition_name: "gpu"
```

The part before the dash must match an existing validation class name (e.g., `K8sNimHelmWorkload`, `SlurmPartition`). The suffix after the dash is a label -- it can be any descriptive string. Each variant runs as a separate test case with its own parameters and appears independently in test results and coverage.

**Rules:**

- Validation class names **cannot** contain dashes, so the first dash always marks the start of a variant suffix.
- The suffix is free-form: `K8sNimHelmWorkload-small`, `SlurmPartition-cpu`, `SlurmGpuAllocation-1gpu` are all valid.
- Each variant is a distinct test entry in coverage tracking.

## Template Variables

### Referencing Step Outputs

Use `{{steps.step_name.field}}` to reference previous step outputs:

```yaml
steps:
  - name: create_instance
    command: "python launch.py"
    # Output: {"instance_id": "i-xxx", "public_ip": "54.1.2.3"}

  - name: test_ssh
    command: "python test_ssh.py"
    args:
      - "--host"
      - "{{steps.create_instance.public_ip}}"
```

### Other Variables

| Variable | Description |
| -------- | ----------- |
| `{{setting_name}}` | From `tests.settings` |
| `{{env.VAR_NAME}}` | Environment variable |
| `{{steps.name.field}}` | Step output field |

## Script Output and Schema Validation

Scripts must output valid JSON to stdout. The output is validated against schemas defined in `output_schemas.py`.

### Schema Auto-Detection

The schema is automatically detected from the step name using a mapping system:

| Step Name Pattern | Schema | Required Fields |
| ----------------- | ------ | --------------- |
| `create_cluster`, `provision_cluster` | `cluster` | `success`, `platform`, `cluster_name`, `node_count` |
| `create_network`, `create_vpc` | `network` | `success`, `platform` |
| `launch_instance`, `create_vm` | `instance` | `success`, `platform`, `instance_id` |
| `run_workload`, `run_test` | `workload_result` | `success`, `platform`, `status` |
| `teardown`, `cleanup`, `destroy` | `teardown` | `success`, `platform` |
| `check_api`, `test_api` | `api_health` | `success`, `platform` |
| `create_access_key` | `access_key` | `success`, `platform`, `access_key_id` |
| `create_tenant` | `tenant` | `success`, `platform`, `tenant_name` |
| `vpc_crud`, `vpc_crud_test` | `vpc_crud` | `success`, `platform` |
| *(unrecognized)* | `generic` | `success`, `platform` |

### Common Required Fields

All schemas require these common fields:

```json
{
  "success": true,
  "platform": "network"
}
```

- `success`: Boolean indicating operation success
- `platform`: Platform type (e.g., `"network"`, `"vm"`, `"iam"`, `"control_plane"`)

### Explicit Schema Override

You can override auto-detection using the `output_schema` field:

```yaml
steps:
  - name: my_custom_step
    command: "python ./my_script.py"
    output_schema: cluster  # Force cluster schema validation
```

### Example Output by Schema Type

**Network schema (`create_network`, `create_vpc`):**

```json
{
  "success": true,
  "platform": "network",
  "network_id": "vpc-0123456789",
  "cidr": "10.0.0.0/16",
  "subnets": [
    {"subnet_id": "subnet-aaa", "cidr": "10.0.1.0/24", "availability_zone": "us-west-2a"}
  ],
  "region": "us-west-2"
}
```

**Cluster schema (`provision_cluster`):**

```json
{
  "success": true,
  "platform": "kubernetes",
  "cluster_name": "my-cluster",
  "node_count": 3,
  "endpoint": "https://cluster.example.com",
  "gpu_count": 8,
  "driver_version": "570.195.03"
}
```

**Teardown schema (`teardown`, `cleanup`):**

```json
{
  "success": true,
  "platform": "network",
  "resources_deleted": ["vpc-123", "subnet-456"],
  "message": "Cleanup completed"
}
```

**Exit codes:**

- `0` = Success
- Non-zero = Failure

### Python Script Example

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

    result = {
        "success": False,
        "platform": "network",
    }

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

### Bash Script Example

```bash
#!/bin/bash
# Create VPC and output JSON

set -e

NAME="${1:-test-vpc}"
REGION="${AWS_REGION:-us-west-2}"

VPC_ID=$(aws ec2 create-vpc \
  --cidr-block 10.0.0.0/16 \
  --region "$REGION" \
  --query 'Vpc.VpcId' \
  --output text)

cat <<EOF
{
  "success": true,
  "platform": "network",
  "network_id": "$VPC_ID",
  "region": "$REGION"
}
EOF
```

## Available Validations

### Generic Validations

| Validation | Parameters | Description |
| ---------- | ---------- | ----------- |
| `FieldExistsCheck` | `step`, `field` or `fields` | Check field(s) exist in output |
| `FieldValueCheck` | `step`, `field`, `expected`, `operator` | Check field value (eq, gt, gte, lt, lte) |
| `StepSuccessCheck` | `step` | Check `success: true` (auto-detects teardown) |

### Network Validations

| Validation | Parameters | Description |
| ---------- | ---------- | ----------- |
| `NetworkProvisionedCheck` | `step` | Check network created with ID |
| `VpcCrudCheck` | `step` | Validate VPC CRUD operations |
| `SubnetConfigCheck` | `step` | Validate subnet configuration |
| `VpcIsolationCheck` | `step` | Validate VPC isolation |
| `SecurityBlockingCheck` | `step` | Validate security blocking |
| `NetworkConnectivityCheck` | `step` | Validate connectivity tests |
| `TrafficFlowCheck` | `step` | Validate traffic flow tests |

### Instance Validations

| Validation | Parameters | Description |
| ---------- | ---------- | ----------- |
| `InstanceStateCheck` | `step`, `expected_state` | Check instance state |
| `InstanceCreatedCheck` | `step` | Check instance was created |

### IAM Validations

| Validation | Parameters | Description |
| ---------- | ---------- | ----------- |
| `AccessKeyCreatedCheck` | `step` | Check access key was created |
| `AccessKeyAuthenticatedCheck` | `step` | Check access key authenticated |
| `AccessKeyDisabledCheck` | `step` | Check access key was disabled |
| `AccessKeyRejectedCheck` | `step` | Check disabled key was rejected |
| `TenantCreatedCheck` | `step` | Check tenant was created |
| `TenantListedCheck` | `step` | Check tenant in list |
| `TenantInfoCheck` | `step` | Check tenant info retrieved |

### Kubernetes Validations

| Validation | Parameters | Description |
| ---------- | ---------- | ----------- |
| `K8sNodeCountCheck` | `count` | Verify node count |
| `K8sNodeReadyCheck` | - | Verify all nodes are Ready |
| `K8sGpuOperatorPodsCheck` | `namespace` | Verify GPU Operator pods running |
| `K8sGpuCapacityCheck` | `expected_per_node`, `expected_total` | Verify GPU capacity |

### Slurm Validations

| Validation | Parameters | Description |
| ---------- | ---------- | ----------- |
| `SlurmInfoAvailable` | - | Verify sinfo command works |
| `SlurmPartition` | `partition_name`, `expected_nodes` | Verify partition exists |
| `SlurmJobSubmission` | `partition` | Test job submission |

## Test Markers

Filter tests using pytest markers:

```bash
# Run only specific tests
isvctl test run -f config.yaml -- -k "vpc_crud"

# Run by marker
isvctl test run -f config.yaml -- -m kubernetes
```

Available markers: `bare_metal`, `kubernetes`, `slurm`, `gpu`, `network`, `hardware`, `software`, `workload`, `l2`, `slow`

## Related Documentation

- [Getting Started](../getting-started.md) - Installation and first steps
- [Local Development](local-development.md) - Running tests locally
