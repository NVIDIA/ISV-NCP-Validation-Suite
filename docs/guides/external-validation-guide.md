# External Validation Guide

This guide explains how to create custom validation tests using the ISV validation framework **without modifying the repository**. You can use `isvctl` as a standalone tool with your own scripts and configuration files.

## Overview

The ISV validation framework uses a **step-based architecture**:

```text
┌────────────────────────────────────────────────────────────────────────────┐
│                        Your Project (External)                             │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐         │
│  │  config.yaml    │    │  scripts/       │    │  Output JSON    │         │
│  │                 │───▶│  provision.py   │───▶│  {"success":    │         │
│  │  - steps        │    │  teardown.py    │    │   true, ...}    │         │
│  │  - validations  │    │  test_api.sh    │    │                 │         │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘         │
│                                                         │                  │
│                                                         ▼                  │
│                                                 ┌─────────────────┐        │
│                                                 │  Validations    │        │
│                                                 │  (built-in)     │        │
│                                                 │  - FieldExists  │        │
│                                                 │  - StepSuccess  │        │
│                                                 │  - SSH checks   │        │
│                                                 └─────────────────┘        │
└────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  isvctl (installed via pip/uv)                                             │
│  - Executes your scripts                                                   │
│  - Validates JSON output against schemas                                   │
│  - Runs built-in validation checks                                         │
│  - Generates test reports                                                  │
└────────────────────────────────────────────────────────────────────────────┘
```

**Key Benefits:**

- **Language-agnostic scripts** - Write in Python, Bash, Go, or any language
- **Schema validation** - Output is validated automatically
- **Built-in validations** - Use ready-made checks for SSH, instances, fields, etc.
- **No code changes** - Everything defined in YAML config and your scripts

---

## Quick Start

### 1. Install isvctl

```bash
# Option 1: From source
# Repository at: https://github.com/NVIDIA/ISV-NCP-Validation-Suite
git clone git@github.com:NVIDIA/ISV-NCP-Validation-Suite.git
cd ISV-NCP-Validation-Suite
uv sync

# Note: Current install from NGC
# See the main README for NGC installation instructions
```

### 2. Create Your Project Structure

```text
my-validations/
├── config.yaml           # Your validation config
├── scripts/
│   ├── provision.py      # Setup script
│   ├── test_api.py       # Test script
│   └── teardown.py       # Cleanup script
└── README.md
```

### 3. Run Validations

```bash
# From your project directory
uv run isvctl test run -f config.yaml

# Or with pip-installed version
isvctl test run -f config.yaml
```

---

## Project Structure

### Recommended Layout

```text
my-cloud-validation/
├── config.yaml                 # Main configuration
├── config-dev.yaml             # Dev overrides (optional)
├── scripts/
│   ├── provision_cluster.py    # Creates resources
│   ├── launch_instance.py      # Launches VM
│   ├── test_connectivity.py    # Tests network
│   └── teardown.py             # Cleans up
├── docs/
│   └── README.md
└── .env                        # Environment variables (gitignored)
```

### Minimal Example

For a simple API health check:

```text
api-check/
├── config.yaml
└── scripts/
    └── check_api.py
```

---

## Writing Scripts

Scripts are the core of your validation. They perform operations and output JSON results.

### Script Requirements

1. **Output valid JSON to stdout** - This is captured and validated
2. **Exit with appropriate code** - `0` for success, non-zero for failure
3. **Write logs/errors to stderr** - Only stdout is captured as JSON
4. **Include required fields** - `success` and `platform` are always required

### Python Script Template

```python
#!/usr/bin/env python3
"""Provision cloud resources.

Usage:
    python provision.py --name my-cluster --region us-west-2

Output JSON:
{
    "success": true,
    "platform": "kubernetes",
    "cluster_name": "my-cluster",
    "node_count": 3,
    "endpoint": "https://..."
}
"""

import argparse
import json
import sys
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision cluster")
    parser.add_argument("--name", required=True, help="Cluster name")
    parser.add_argument("--region", default="us-west-2", help="Region")
    parser.add_argument("--node-count", type=int, default=3, help="Number of nodes")
    args = parser.parse_args()

    # Initialize result with required fields
    result: dict[str, Any] = {
        "success": False,
        "platform": "kubernetes",  # or "vm", "network", etc.
    }

    try:
        # Your provisioning logic here
        # e.g., call cloud APIs, run terraform, etc.

        # On success, populate result
        result["success"] = True
        result["cluster_name"] = args.name
        result["node_count"] = args.node_count
        result["endpoint"] = f"https://{args.name}.example.com"
        result["region"] = args.region

    except Exception as e:
        # Log error to stderr (not stdout)
        print(f"Error: {e}", file=sys.stderr)
        result["error"] = str(e)

    # Output JSON to stdout
    print(json.dumps(result, indent=2))

    # Return exit code
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
```

### Bash Script Template

```bash
#!/bin/bash
# Launch VM instance
# Usage: ./launch_instance.sh --name test-vm --region us-west-2

set -euo pipefail

# Parse arguments
NAME=""
REGION="us-west-2"
INSTANCE_TYPE="g5.xlarge"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --name) NAME="$2"; shift 2 ;;
        --region) REGION="$2"; shift 2 ;;
        --instance-type) INSTANCE_TYPE="$2"; shift 2 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

# Validate required args
if [[ -z "$NAME" ]]; then
    echo '{"success": false, "platform": "vm", "error": "Name is required"}'
    exit 1
fi

# Your provisioning logic (example with AWS CLI)
INSTANCE_ID=$(aws ec2 run-instances \
    --image-id ami-0123456789 \
    --instance-type "$INSTANCE_TYPE" \
    --region "$REGION" \
    --query 'Instances[0].InstanceId' \
    --output text 2>/dev/null) || {
    echo '{"success": false, "platform": "vm", "error": "Failed to launch instance"}'
    exit 1
}

# Wait for running state
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID" --region "$REGION" 2>/dev/null

# Get public IP
PUBLIC_IP=$(aws ec2 describe-instances \
    --instance-ids "$INSTANCE_ID" \
    --region "$REGION" \
    --query 'Reservations[0].Instances[0].PublicIpAddress' \
    --output text 2>/dev/null)

# Output JSON (success case)
cat <<EOF
{
  "success": true,
  "platform": "vm",
  "instance_id": "$INSTANCE_ID",
  "instance_type": "$INSTANCE_TYPE",
  "public_ip": "$PUBLIC_IP",
  "state": "running",
  "region": "$REGION"
}
EOF
```

### Terraform Wrapper Script

```python
#!/usr/bin/env python3
"""Run Terraform and output JSON inventory."""

import json
import subprocess
import sys


def main() -> int:
    result = {
        "success": False,
        "platform": "kubernetes",
    }

    try:
        # Run terraform apply
        subprocess.run(
            ["terraform", "apply", "-auto-approve"],
            check=True,
            capture_output=True,
            text=True,
        )

        # Get outputs
        tf_output = subprocess.run(
            ["terraform", "output", "-json"],
            capture_output=True,
            text=True,
            check=True,
        )
        outputs = json.loads(tf_output.stdout)

        # Map terraform outputs to expected schema
        result["success"] = True
        result["cluster_name"] = outputs.get("cluster_name", {}).get("value")
        result["node_count"] = outputs.get("node_count", {}).get("value")
        result["endpoint"] = outputs.get("endpoint", {}).get("value")

    except subprocess.CalledProcessError as e:
        print(f"Terraform failed: {e.stderr}", file=sys.stderr)
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
```

---

## Configuration File

### Basic Structure

```yaml
version: "1.0"

commands:
  # Platform name (matches tests.platform)
  myplatform:
    # Phases execute in order
    phases: ["setup", "teardown"]

    steps:
      # Each step runs a script
      - name: provision_cluster
        phase: setup
        command: "python3 ./scripts/provision.py"
        args:
          - "--name"
          - "{{cluster_name}}"
          - "--region"
          - "{{region}}"
        timeout: 600

      - name: teardown
        phase: teardown
        command: "python3 ./scripts/teardown.py"
        args:
          - "--cluster-id"
          - "{{steps.provision_cluster.cluster_id}}"
        timeout: 300

  # Skip unused platforms
  kubernetes:
    skip: true
  slurm:
    skip: true

tests:
  platform: myplatform
  cluster_name: "my-validation"

  # Variables available in templates
  settings:
    region: "us-west-2"
    cluster_name: "test-cluster"
    instance_type: "g5.xlarge"

  # Validations run after steps complete
  validations:
    cluster_checks:
      step: provision_cluster
      checks:
        - StepSuccessCheck: {}
        - FieldExistsCheck:
            fields: ["cluster_id", "endpoint"]

    teardown_checks:
      step: teardown
      checks:
        - StepSuccessCheck: {}
```

### Step Configuration Options

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `name` | Yes | - | Unique identifier for the step |
| `phase` | No | `setup` | Phase this step belongs to |
| `command` | Yes | - | Script/command to execute |
| `args` | No | `[]` | Command arguments (supports templates) |
| `timeout` | No | `300` | Timeout in seconds |
| `env` | No | `{}` | Environment variables |
| `skip` | No | `false` | Skip this step |
| `continue_on_failure` | No | `false` | Continue even if step fails |
| `output_schema` | No | auto | Schema for output validation |

### Template Variables

Use Jinja2 templates to reference values:

```yaml
# Reference settings
"{{region}}"                          # From tests.settings.region

# Reference step outputs
"{{steps.provision.cluster_id}}"      # Output from previous step
"{{steps.provision.nodes | join(',')}}"  # Join array values

# Reference environment variables
"{{env.AWS_REGION}}"                  # Environment variable

# Conditionals
"{{(env.SKIP_TEARDOWN == 'true') | ternary('--skip', '')}}"

# Defaults
"{{region | default('us-west-2')}}"
```

---

## Output Schemas

Scripts must output JSON with specific fields. Different schemas have different required fields depending on the operation type.

### Common Fields

All schemas share these common properties:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `success` | boolean | **Yes** | Whether the operation succeeded |
| `platform` | string | **Yes** | Platform type: `kubernetes`, `slurm`, `bare_metal`, `network`, `vm`, `iam`, or `iso` |

**Note:** The `cluster_name` field is required only for certain schemas (e.g., `cluster`). Each schema has its own required fields - see the schema-specific sections below.

### Schema Types and Required Fields

Different step types use different schemas. The schema is auto-detected from the step name or can be explicitly set via `output_schema`.

#### Cluster Schema (`cluster`)

Used for: `provision_cluster`, `create_cluster`, `setup_cluster`

**Required:** `success`, `platform`, `cluster_name`, `node_count`

| Field | Type | Description |
|-------|------|-------------|
| `cluster_name` | string | Name of the cluster |
| `endpoint` | string | Cluster API endpoint |
| `node_count` | int | Total number of nodes |
| `nodes` | array | List of node names |
| `gpu_count` | int | Total GPUs in cluster |
| `gpu_per_node` | int | GPUs per node |
| `driver_version` | string | NVIDIA driver version |
| `kubeconfig_path` | string | Path to kubeconfig file |

#### Instance Schema (`instance`)

Used for: `launch_instance`, `create_instance`, `provision_vm`, `create_vm`

**Required:** `success`, `platform`, `instance_id`

| Field | Type | Description |
|-------|------|-------------|
| `instance_id` | string | Instance identifier |
| `state` | string | Instance state: `pending`, `running`, `stopped`, `terminated` |
| `public_ip` | string | Public IP address |
| `private_ip` | string | Private IP address |
| `instance_type` | string | Instance type/size |
| `ssh_user` | string | SSH username |
| `ssh_key_path` | string | Path to SSH private key |

#### Network Schema (`network`)

Used for: `create_network`, `provision_network`, `create_vpc`, `setup_network`

**Required:** `success`, `platform`

| Field | Type | Description |
|-------|------|-------------|
| `network_id` | string | Network/VPC identifier |
| `cidr` | string | CIDR block for the network |
| `region` | string | Cloud region |
| `subnets` | array | List of subnets with `subnet_id`, `cidr`, `availability_zone` |

#### Teardown Schema (`teardown`)

Used for: `teardown`, `cleanup`, `destroy`

**Required:** `success`, `platform`

| Field | Type | Description |
|-------|------|-------------|
| `resources_deleted` | array | List of resources that were deleted |
| `resources_failed` | array | List of resources that failed to delete |
| `message` | string | Teardown status message |
| `duration_seconds` | number | Teardown duration |

#### GPU Setup Schema (`gpu_setup`)

Used for: `install_gpu_operator`, `setup_gpu`, `install_drivers`

**Required:** `success`, `platform`, `installed`

| Field | Type | Description |
|-------|------|-------------|
| `installed` | boolean | Whether GPU setup completed |
| `driver_version` | string | NVIDIA driver version |
| `cuda_version` | string | CUDA version |
| `gpu_count` | int | Number of GPUs |
| `gpu_model` | string | GPU model name |

#### Workload Result Schema (`workload_result`)

Used for: `run_workload`, `run_test`, `run_benchmark`, `execute_workload`

**Required:** `success`, `platform`, `status`

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | Workload status: `passed`, `failed`, `skipped` |
| `duration_seconds` | number | Execution duration |
| `metrics` | object | Workload metrics (bandwidth, latency, etc.) |
| `logs` | string | Workload output logs |

### Platform Output Schemas

These are used for the main command output that becomes the test inventory.

#### Kubernetes Platform

| Field | Type | Description |
|-------|------|-------------|
| `driver_version` | string | NVIDIA driver version |
| `node_count` | int | Total number of nodes |
| `nodes` | array | List of node names or node objects |
| `gpu_node_count` | int | Number of GPU nodes |
| `gpu_per_node` | int | GPUs per node |
| `total_gpus` | int | Total GPUs in cluster |
| `control_plane_address` | string | Control plane IP/hostname |
| `kubeconfig_path` | string | Path to kubeconfig file |
| `gpu_operator_namespace` | string | GPU operator namespace (default: "nvidia-gpu-operator") |
| `runtime_class` | string | RuntimeClass for GPU pods (default: "nvidia") |
| `gpu_resource_name` | string | GPU resource name (default: "nvidia.com/gpu") |

#### VM Platform

| Field | Type | Description |
|-------|------|-------------|
| `region` | string | Cloud region |
| `account_id` | string | Cloud account ID |
| `description` | string | VM test description |

*Note: For instance-level validations (SSH, state checks), use the instance schema fields.*

#### Network Platform

| Field | Type | Description |
|-------|------|-------------|
| `region` | string | Cloud region |
| `description` | string | Network test description |

#### Slurm Platform

| Field | Type | Description |
|-------|------|-------------|
| `partitions` | object | Partition configurations (name → {nodes, node_count}) |
| `default_partition` | string | Default partition name |
| `cuda_arch` | string | CUDA compute capability |
| `storage_path` | string | Scratch storage path (default: "/tmp") |

#### Bare Metal Platform

| Field | Type | Description |
|-------|------|-------------|
| `hostname` | string | Server hostname |
| `gpu_count` | int | Number of GPUs |
| `driver_version` | string | NVIDIA driver version |
| `cuda_version` | string | CUDA version |

#### IAM Platform

| Field | Type | Description |
|-------|------|-------------|
| `provider` | string | IAM provider (e.g., 'aws-iam', 'okta') |
| `api_endpoint` | string | IAM API endpoint URL |
| `user_count` | int | Number of existing users |
| `roles` | array | Available roles |
| `supports_mfa` | bool | Whether MFA is supported |
| `supports_service_accounts` | bool | Whether service accounts are supported |
| `auth_methods` | array | Supported auth methods |

#### ISO Platform

| Field | Type | Description |
|-------|------|-------------|
| `provider` | string | Import provider (e.g., 'aws_vm_import') |
| `region` | string | Cloud region |
| `account_id` | string | Cloud account ID |
| `default_image_url` | string | Default image URL to download |
| `supported_formats` | array | Supported image formats (vmdk, vhd, ova, raw) |
| `gpu_instance_types` | array | Supported GPU instance types |

### Example Outputs

**Cluster Schema (Kubernetes):**

```json
{
  "success": true,
  "platform": "kubernetes",
  "cluster_name": "my-cluster",
  "node_count": 3,
  "nodes": ["node-1", "node-2", "node-3"],
  "gpu_count": 12,
  "gpu_per_node": 4,
  "driver_version": "570.195.03",
  "kubeconfig_path": "/home/user/.kube/config"
}
```

**Instance Schema (VM/EC2):**

```json
{
  "success": true,
  "platform": "vm",
  "instance_id": "i-0abc123def456",
  "instance_type": "g5.xlarge",
  "public_ip": "54.1.2.3",
  "private_ip": "10.0.1.5",
  "state": "running",
  "ssh_key_path": "/home/user/.ssh/my-key.pem",
  "ssh_user": "ubuntu"
}
```

**Network Schema:**

```json
{
  "success": true,
  "platform": "network",
  "network_id": "vpc-0abc123",
  "cidr": "10.0.0.0/16",
  "region": "us-west-2",
  "subnets": [
    {"subnet_id": "subnet-1", "cidr": "10.0.1.0/24", "availability_zone": "us-west-2a"},
    {"subnet_id": "subnet-2", "cidr": "10.0.2.0/24", "availability_zone": "us-west-2b"}
  ]
}
```

**Teardown Schema:**

```json
{
  "success": true,
  "platform": "vm",
  "resources_deleted": ["i-0abc123", "sg-0xyz789"],
  "message": "All resources cleaned up successfully",
  "duration_seconds": 45.2
}
```

### Success and Error Fields

The `success` field is **required** by most schemas and is used by `StepSuccessCheck`:

```json
{
  "success": true,
  "platform": "vm",
  "instance_id": "i-abc123",
  ...
}
```

On failure, include an `error` field with details:

```json
{
  "success": false,
  "platform": "vm",
  "error": "Failed to launch instance: quota exceeded"
}
```

---

## Built-in Validations

Use these in your `tests.validations` section without writing code.

### Generic Validations

| Validation | Description | Config Options |
|------------|-------------|----------------|
| `StepSuccessCheck` | Check step completed successfully | - |
| `FieldExistsCheck` | Check required fields exist in output | `fields` (list) or `field` (string) |
| `FieldValueCheck` | Check field has expected value | `field`, `expected`, `operator`, `contains`, `min`, `max` |
| `SchemaValidation` | Validate output matches JSON schema | `schema` (string) |

**StepSuccessCheck** checks for:

- `success: true` (boolean) - most common
- `status: "passed"` or `status: "skipped"` - alternative

**FieldValueCheck operators**: `eq` (default), `gt`, `gte`, `lt`, `lte`

```yaml
validations:
  generic_checks:
    step: provision_cluster
    checks:
      # Check step succeeded (success: true)
      - StepSuccessCheck: {}

      # Check fields exist in output
      - FieldExistsCheck:
          fields: ["cluster_id", "endpoint", "node_count"]

      # Check field has expected value
      - FieldValueCheck:
          field: "node_count"
          expected: 3
          operator: "gte"  # eq, gt, gte, lt, lte

      # Check string contains substring
      - FieldValueCheck:
          field: "endpoint"
          contains: "kubernetes"

      # Check number in range
      - FieldValueCheck:
          field: "node_count"
          min: 1
          max: 10
```

### Instance Validations

| Validation | Description | Required Step Output | Config Options |
|------------|-------------|---------------------|----------------|
| `InstanceStateCheck` | Check instance is in expected state | `instance_id`, `state` | `expected_state` (default: "running") |
| `InstanceCreatedCheck` | Check instance was created | `instance_id` | - |

Optional step output fields for `InstanceCreatedCheck`: `public_ip`, `private_ip`, `instance_type`

```yaml
validations:
  instance_checks:
    step: launch_instance
    checks:
      # Check instance is in expected state
      - InstanceStateCheck:
          expected_state: "running"

      # Check instance was created (reports instance details)
      - InstanceCreatedCheck: {}
```

### SSH Validations

All SSH validations require connection details from step output. Multiple field name alternatives are supported.

| Validation | Description | Config Options |
|------------|-------------|----------------|
| `SshConnectivityCheck` | Test SSH connectivity and basic commands | `user` (default: "ubuntu") |
| `SshOsCheck` | Check OS details via SSH | `expected_os` (e.g., "ubuntu", "rhel") |
| `SshCpuInfoCheck` | Check CPU, NUMA topology, and PCI devices | - |
| `SshGpuCheck` | Test GPU visibility via nvidia-smi | `expected_gpus` (default: 1) |
| `SshDriverCheck` | Check kernel and NVIDIA driver versions | `expected_driver_version` |
| `SshGpuStressCheck` | Run GPU stress test (placeholder) | `duration` |
| `SshContainerRuntimeCheck` | Check Docker and NVIDIA container runtime | `ngc_api_key` |

**SSH connection field alternatives** (any of these work):

- **Host**: `host`, `ssh_host`, `public_ip`, `private_ip`
- **Key**: `key_file`, `key_path`, `ssh_key_path`
- **User**: `user`, `ssh_user` (default: "ubuntu")

```yaml
validations:
  ssh_checks:
    step: launch_instance
    checks:
      # Test SSH connectivity
      - SshConnectivityCheck: {}

      # Check OS type
      - SshOsCheck:
          expected_os: "ubuntu"

      # Check CPU and PCI configuration
      - SshCpuInfoCheck: {}

      # Check GPU visibility (expects nvidia-smi)
      - SshGpuCheck:
          expected_gpus: 1

      # Check driver version
      - SshDriverCheck:
          expected_driver_version: "550"

      # Check Docker and NVIDIA container runtime
      - SshContainerRuntimeCheck:
          ngc_api_key: "{{env.NGC_API_KEY}}"
```

### Network Validations

| Validation | Description | Required Step Output | Config Options |
|------------|-------------|---------------------|----------------|
| `NetworkProvisionedCheck` | Check network/VPC was provisioned | `network_id` | - |
| `VpcCrudCheck` | Validate VPC CRUD operations | `tests` (dict with CRUD results) | - |
| `SubnetConfigCheck` | Validate subnet configuration | `tests`, `subnets` | `min_subnets` (default: 2), `require_multi_az` (default: true) |
| `VpcIsolationCheck` | Validate VPC isolation | `tests` (isolation checks) | - |
| `SecurityBlockingCheck` | Validate security rules | `tests` (security checks) | - |
| `NetworkConnectivityCheck` | Validate network connectivity | `instances` (list) | - |
| `TrafficFlowCheck` | Validate traffic flow | `tests` (traffic checks) | - |

**Expected `tests` structure for VpcCrudCheck:**

- `create_vpc`, `read_vpc`, `update_tags`, `update_dns`, `delete_vpc` - each with `passed: true/false`

**Expected `tests` structure for VpcIsolationCheck:**

- `no_peering`, `no_cross_routes_a`, `no_cross_routes_b`, `sg_isolation_*`

**Expected `tests` structure for SecurityBlockingCheck:**

- `sg_default_deny_inbound`, `sg_allows_specific_ssh`, `sg_denies_vpc_icmp`, `nacl_explicit_deny`, `sg_restricted_egress`

**Expected `tests` structure for TrafficFlowCheck:**

- `traffic_allowed`, `traffic_blocked`, `internet_icmp`, `internet_http`

```yaml
validations:
  network_checks:
    checks:
      # Check network was provisioned
      - NetworkProvisionedCheck:
          step: create_network

      # Check VPC CRUD operations
      - VpcCrudCheck:
          step: vpc_crud

      # Check subnet configuration
      - SubnetConfigCheck:
          step: subnet_config
          min_subnets: 4
          require_multi_az: true

      # Check VPC isolation
      - VpcIsolationCheck:
          step: vpc_isolation

      # Check security blocking rules
      - SecurityBlockingCheck:
          step: security_blocking

      # Check instance connectivity
      - NetworkConnectivityCheck:
          step: connectivity_test

      # Check traffic flow
      - TrafficFlowCheck:
          step: traffic_validation
```

### Kubernetes Validations

These validations query the cluster directly via `kubectl` - they don't depend on step output fields.

| Validation | Description | Config Options |
|------------|-------------|----------------|
| `K8sNodeCountCheck` | Verify expected number of nodes | `count` (required) |
| `K8sNodeReadyCheck` | Verify all nodes are Ready | `require_all_ready` (default: true) |
| `K8sExpectedNodesCheck` | Verify specific nodes are present | `names` (list), `allow_unexpected_nodes` (default: true) |
| `K8sGpuCapacityCheck` | Check node-level GPU capacity | `expected_total`, `expected_per_node`, `resource_name` |
| `K8sGpuOperatorPodsCheck` | Check GPU Operator pods are running | `namespace` |
| `K8sGpuOperatorNamespaceCheck` | Verify GPU Operator namespace exists | `namespace` |
| `K8sGpuLabelsCheck` | Verify GPU nodes have NVIDIA labels | `label_selector` (default: "nvidia.com/gpu.present=true") |
| `K8sNvidiaSmiCheck` | Run nvidia-smi on all GPU nodes | `timeout`, `cuda_image`, `runtime_class` |
| `K8sDriverVersionCheck` | Verify NVIDIA driver version | `driver_version` (required), `timeout` |
| `K8sGpuPodAccessCheck` | Verify GPU access from pods | `gpu_count` (per node), `total_gpu_count`, `timeout` |
| `K8sPodHealthCheck` | Verify pods are Running/Succeeded | `ignore_phases` (list of phases to ignore) |
| `K8sNoPendingPodsCheck` | Verify no pods stuck in Pending | - |
| `K8sNoErrorPodsCheck` | Verify no pods in error state | `error_states` (default: Error, CrashLoopBackOff, ImagePullBackOff, etc.) |

```yaml
validations:
  k8s_checks:
    step: provision_cluster
    checks:
      # Check node count (supports Jinja2 templating)
      - K8sNodeCountCheck:
          count: "{{steps.provision_cluster.node_count}}"

      # Check all nodes are Ready
      - K8sNodeReadyCheck:
          require_all_ready: true

      # Check expected nodes are present
      - K8sExpectedNodesCheck:
          names: ["node-1", "node-2", "node-3"]
          allow_unexpected_nodes: true

      # Check GPU capacity at node level
      - K8sGpuCapacityCheck:
          expected_total: 8
          expected_per_node: 4
          resource_name: "nvidia.com/gpu"  # default

      # Check GPU Operator pods are running
      - K8sGpuOperatorPodsCheck:
          namespace: "nvidia-gpu-operator"

      # Run nvidia-smi on all GPU nodes via ephemeral pods
      - K8sNvidiaSmiCheck:
          timeout: 60
          runtime_class: "nvidia"  # for MicroK8s

      # Verify driver version
      - K8sDriverVersionCheck:
          driver_version: "550.90.07"
          timeout: 60

      # Check no pods in error state
      - K8sNoErrorPodsCheck:
          error_states: ["Error", "CrashLoopBackOff", "ImagePullBackOff"]
```

### Cluster Validations (Step Output Based)

These validations check step output fields (not live cluster state).

| Validation | Description | Required Step Output | Config Options |
|------------|-------------|---------------------|----------------|
| `NodeCountCheck` | Check node count matches expected | `node_count` | `expected` (required) |
| `ClusterHealthCheck` | Check cluster is healthy | `cluster_name`, `node_count` (> 0) | - |
| `GpuOperatorInstalledCheck` | Check GPU operator installation | `installed` (bool) | - |
| `PerformanceCheck` | Check performance metrics | `metrics` (dict) | `min_bandwidth_gbps`, `max_latency_ms` |

```yaml
validations:
  cluster_checks:
    step: provision_cluster
    checks:
      # Check cluster is healthy (has name and nodes > 0)
      - ClusterHealthCheck: {}

      # Check exact node count
      - NodeCountCheck:
          expected: 3

      # Check GPU operator (from gpu_setup step)
      - GpuOperatorInstalledCheck:
          step: install_gpu_operator

      # Check performance metrics (from workload step)
      - PerformanceCheck:
          step: run_benchmark
          min_bandwidth_gbps: 100
          max_latency_ms: 5
```

### IAM Validations

| Validation | Description | Required Step Output |
|------------|-------------|---------------------|
| `AccessKeyCreatedCheck` | Check access key was created | `access_key_id`, `username` |
| `AccessKeyAuthenticatedCheck` | Check key can authenticate | `authenticated` (bool) |
| `AccessKeyDisabledCheck` | Check key was disabled | `status` (should be "Inactive") |
| `AccessKeyRejectedCheck` | Check disabled key is rejected | `rejected` (bool) |
| `TenantCreatedCheck` | Check tenant was created | `tenant_name` (or `group_name`), `tenant_id` (or `group_id`) |
| `TenantListedCheck` | Check tenant appears in list | `found_target` (bool), `target_tenant` |
| `TenantInfoCheck` | Check tenant info retrieved | `tenant_name`, `tenant_id` |

```yaml
validations:
  iam_checks:
    checks:
      # Check access key was created
      - AccessKeyCreatedCheck:
          step: create_access_key

      # Check key can authenticate
      - AccessKeyAuthenticatedCheck:
          step: test_access_key

      # Check key was disabled
      - AccessKeyDisabledCheck:
          step: disable_access_key

      # Check disabled key is rejected
      - AccessKeyRejectedCheck:
          step: verify_key_rejected

      # Check tenant was created
      - TenantCreatedCheck:
          step: create_tenant

      # Check tenant appears in list
      - TenantListedCheck:
          step: list_tenants

      # Check tenant info
      - TenantInfoCheck:
          step: get_tenant
```

---

## Validation Groups

Validations are grouped by meaningful category names. Two configuration formats are supported.

### Format 1: Group Defaults with `checks` List

Set `step` and `phase` at the group level - they apply to all checks in that group:

```yaml
validations:
  # Group-level step applies to all checks
  setup_checks:
    step: provision_cluster
    checks:
      - StepSuccessCheck: {}
      - FieldExistsCheck:
          fields: ["cluster_id", "endpoint"]
      - ClusterHealthCheck: {}

  # Runs after teardown phase completes
  teardown_checks:
    step: teardown
    checks:
      - StepSuccessCheck: {}
```

### Format 2: List Format with Per-Check `step`

Each validation specifies its own `step`:

```yaml
validations:
  network:
    checks:
      - VpcCrudCheck:
          step: vpc_crud
      - SubnetConfigCheck:
          step: subnet_config
          min_subnets: 4
      - NetworkProvisionedCheck:
          step: create_network
```

### Controlling Validation Timing

Use `phase` to control when validations execute:

| `phase` | When validations run |
|-------------|---------------------|
| *(not set)* | After setup steps complete (default) |
| `test` | After test steps complete |
| `teardown` | After teardown steps complete |

```yaml
validations:
  # Runs after setup (default)
  setup_checks:
    step: provision_cluster
    checks:
      - StepSuccessCheck: {}

  # Runs after teardown phase
  cleanup_checks:
    step: teardown
    checks:
      - StepSuccessCheck: {}
```

### Mixing Group Defaults with Per-Check Overrides

Individual checks can override group-level `step`:

```yaml
validations:
  all_checks:
    step: provision_cluster  # Default for this group
    checks:
      - ClusterHealthCheck: {}  # Uses group default
      - StepSuccessCheck:
          step: teardown  # Overrides group default
```

---

## Complete Example

Here's a full example for validating a custom cloud VM:

### config.yaml

```yaml
version: "1.0"

commands:
  mycloud:
    phases: ["setup", "teardown"]
    steps:
      # Step 1: Launch GPU VM
      - name: launch_instance
        phase: setup
        command: "python3 ./scripts/launch_vm.py"
        args:
          - "--name"
          - "gpu-test-vm"
          - "--instance-type"
          - "{{instance_type}}"
          - "--region"
          - "{{region}}"
        timeout: 600
        output_schema: instance  # Explicit schema (or auto-detected from step name)

      # Step 2: Cleanup
      - name: teardown
        phase: teardown
        command: "python3 ./scripts/teardown.py"
        args:
          - "--instance-id"
          - "{{steps.launch_instance.instance_id}}"
          - "--region"
          - "{{region}}"
        timeout: 300
        output_schema: teardown

  # Skip unused platforms
  kubernetes:
    skip: true
  slurm:
    skip: true

tests:
  platform: mycloud
  cluster_name: "mycloud-gpu-validation"

  settings:
    region: "us-west-2"
    instance_type: "gpu.large"

  validations:
    # Validate VM launched successfully
    vm_launch:
      step: launch_instance
      checks:
        - StepSuccessCheck: {}
        - FieldExistsCheck:
            fields: ["instance_id", "public_ip", "ssh_key_path"]
        - InstanceStateCheck:
            expected_state: "running"
        - InstanceCreatedCheck: {}

    # Validate SSH and GPU
    ssh:
      step: launch_instance
      checks:
        - SshConnectivityCheck: {}
        - SshOsCheck:
            expected_os: "ubuntu"
        - SshCpuInfoCheck: {}
        - SshGpuCheck:
            expected_gpus: 1
        - SshDriverCheck: {}

    # Validate teardown
    cleanup:
      step: teardown
      checks:
        - StepSuccessCheck: {}

  exclude:
    markers:
      - kubernetes
      - slurm
      - workload
```

### scripts/launch_vm.py

```python
#!/usr/bin/env python3
"""Launch GPU VM on MyCloud.

Output matches the 'instance' schema:
- Required: success, platform, instance_id
- Optional: state, public_ip, private_ip, instance_type, ssh_user, ssh_key_path
"""

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--instance-type", default="gpu.large")
    parser.add_argument("--region", default="us-west-2")
    args = parser.parse_args()

    result: dict = {
        "success": False,
        "platform": "vm",
    }

    try:
        # Your cloud SDK calls here
        # Example: mycloud_client.create_instance(...)

        # Simulate successful launch
        instance_id = "inst-abc123"
        public_ip = "54.1.2.3"

        # Create SSH key (save to ~/.ssh/)
        key_dir = Path.home() / ".ssh"
        key_dir.mkdir(exist_ok=True)
        key_path = key_dir / f"mycloud-{instance_id}.pem"
        key_path.write_text("-----BEGIN RSA PRIVATE KEY-----\n...\n")
        key_path.chmod(0o600)

        result.update({
            "success": True,
            "instance_id": instance_id,
            "instance_type": args.instance_type,
            "public_ip": public_ip,
            "private_ip": "10.0.1.5",
            "state": "running",
            "ssh_key_path": str(key_path),  # Matches schema field name
            "ssh_user": "ubuntu",
            "region": args.region,
        })

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
```

### scripts/teardown.py

```python
#!/usr/bin/env python3
"""Teardown MyCloud resources.

Output matches the 'teardown' schema:
- Required: success, platform
- Optional: resources_deleted, resources_failed, message, duration_seconds
"""

import argparse
import json
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--region", default="us-west-2")
    args = parser.parse_args()

    start_time = time.time()

    result: dict = {
        "success": False,
        "platform": "vm",
        "resources_deleted": [],
        "resources_failed": [],
    }

    try:
        # Your cloud SDK calls here
        # Example: mycloud_client.terminate_instance(args.instance_id)

        result["success"] = True
        result["resources_deleted"].append(args.instance_id)
        result["message"] = "All resources cleaned up successfully"

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        result["error"] = str(e)
        result["resources_failed"].append(args.instance_id)

    result["duration_seconds"] = time.time() - start_time

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
```

---

## Running Validations

### Basic Usage

```bash
# Run all phases
isvctl test run -f config.yaml

# Verbose output
isvctl test run -f config.yaml -v

# Dry run (validate config without executing)
isvctl test run -f config.yaml --dry-run

# Run specific phase only
isvctl test run -f config.yaml --phase setup
isvctl test run -f config.yaml --phase test
isvctl test run -f config.yaml --phase teardown
```

### Filtering Tests

```bash
# Run specific validation by name
isvctl test run -f config.yaml -- -k "SshConnectivity"

# Run by marker
isvctl test run -f config.yaml -- -m gpu

# Exclude slow tests
isvctl test run -f config.yaml -- -m "not slow"
```

### Config Overrides

```bash
# Merge configs (later overrides earlier)
isvctl test run -f base.yaml -f overrides.yaml

# Override specific values
isvctl test run -f config.yaml --set tests.settings.region=us-east-1
```

### Environment Variables

```bash
# Pass credentials via environment
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_REGION=us-west-2

isvctl test run -f config.yaml
```

---

## Best Practices

### Script Design

1. **Always output valid JSON** - Even on failure, output `{"success": false, "error": "..."}`
2. **Log to stderr** - Keep stdout clean for JSON output
3. **Handle timeouts gracefully** - Check for partial state and clean up
4. **Include all fields** - Always include `success` and `platform`

### Configuration

1. **Use settings for reusable values** - `region`, `instance_type`, etc.
2. **Group related validations** - Use meaningful group names
3. **Set appropriate timeouts** - Account for cloud API latency
4. **Use templates for dependencies** - `{{steps.prev.field}}`

### Testing

1. **Test scripts manually first** - Run scripts standalone to verify JSON output
2. **Use dry-run** - Validate config before running
3. **Start with setup phase only** - Debug incrementally
4. **Keep teardown simple** - Clean up should be idempotent

### Security

1. **Never hardcode credentials** - Use environment variables
2. **Gitignore sensitive files** - `.env`, `*.pem`, state files
3. **Use IAM roles where possible** - Avoid long-lived credentials

---

## Troubleshooting

### Script Output Issues

```bash
# Test script manually
python ./scripts/provision.py --name test --region us-west-2

# Verify JSON is valid
python ./scripts/provision.py --name test 2>/dev/null | jq .
```

### Schema Validation Failures

Check required fields for each schema:

```bash
# Schema required fields:
# cluster:          success, platform, cluster_name, node_count
# instance:         success, platform, instance_id
# network:          success, platform
# teardown:         success, platform
# gpu_setup:        success, platform, installed
# workload_result:  success, platform, status
```

Common issues:

- Missing `success` field (required by most schemas)
- Wrong field names (e.g., `key_path` vs `ssh_key_path`)
- Invalid `state` values (must be: pending, running, stopped, terminated)

### SSH Validation Failures

Ensure your script output includes SSH connection fields. Any of these alternatives work:

```json
{
  "public_ip": "54.1.2.3",     // or: host, ssh_host, private_ip
  "ssh_key_path": "/path/to/key.pem",  // or: key_file, key_path
  "ssh_user": "ubuntu"         // or: user (default: "ubuntu")
}
```

Common issues:

- Key file doesn't exist or wrong permissions (should be 0600)
- Wrong SSH user for the AMI/image
- Security group doesn't allow SSH (port 22)
- Instance not in "running" state yet

### Debug Mode

```bash
# Show full output on failure
isvctl test run -f config.yaml -v -- -s --tb=long
```

---

## Related Documentation

- [Configuration Guide](configuration.md) - Full config reference
- [isvctl Package](../packages/isvctl.md) - CLI documentation
- [Local Development](local-development.md) - Development setup
