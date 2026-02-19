# AWS Bare Metal (BMaaS) Validation Guide

Validates AWS EC2 bare-metal GPU instances using the ISV validation framework.

## Overview

The AWS BM validation tests verify:

1. **Instance Lifecycle** - Provisioning, state verification, instance listing, deletion
2. **SSH Access** - Remote connectivity via SSH
3. **Host OS Validation** - Kernel, BIOS, NVIDIA drivers
4. **GPU Tests** - GPU visibility, stress workloads
5. **Reboot Resilience** - Instance reboot, recovery, full host OS persistence
6. **NIM Inference** - NIM container deployment, health, model listing, inference
7. **Sanitization** - Resource cleanup verification after teardown

## Prerequisites

### Required Tools

- AWS CLI v2 (`aws`)
- Python 3.12+ with boto3, paramiko
- uv package manager

### AWS Credentials

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_REGION=us-west-2
```

### Required IAM Permissions

Same as VM validation. See [AWS VM Guide](../../vm/docs/aws-vm.md) for the full IAM policy.

## Quick Start

```bash
# Run all tests (provisions g4dn.metal by default)
uv run isvctl test run -f isvctl/configs/aws-bm.yaml

# Verbose output
uv run isvctl test run -f isvctl/configs/aws-bm.yaml -- -v -s

# Run only SSH tests
uv run isvctl test run -f isvctl/configs/aws-bm.yaml -- -k "Ssh"

# Run only reboot validations
uv run isvctl test run -f isvctl/configs/aws-bm.yaml -- -k "reboot"
```

## Dev Workflow (Instance Reuse)

Bare-metal instances take ~3 min to provision and ~20 min to terminate.
For fast iteration during development, you can keep the instance alive
between runs.

```bash
# Run 1: launch + test, keep instance alive
AWS_BM_SKIP_TEARDOWN=true uv run isvctl test run -f isvctl/configs/aws-bm.yaml -- -v -s

# Run 2+: reuse existing instance (get instance ID from run 1 output)
AWS_BM_INSTANCE_ID=i-xxx AWS_BM_KEY_FILE=/tmp/isv-bm-test-key.pem \
  AWS_BM_SKIP_TEARDOWN=true uv run isvctl test run -f isvctl/configs/aws-bm.yaml -- -v -s

# Final: teardown (unset skip flag)
AWS_BM_INSTANCE_ID=i-xxx AWS_BM_KEY_FILE=/tmp/isv-bm-test-key.pem \
  uv run isvctl test run -f isvctl/configs/aws-bm.yaml -- -v -s
```

## Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `region` | string | `us-west-2` | AWS region |
| `instance_type` | string | `g4dn.metal` | Bare-metal instance type |

### Available Bare-Metal GPU Instance Types

| Instance Type | GPUs | GPU Type | vCPUs | Memory |
|---------------|------|----------|-------|--------|
| g4dn.metal | 8 | T4 | 96 | 384 GiB |
| g5g.metal | 2 | T4g | 64 | 128 GiB |

## Test Duration

| Phase | Duration | Description |
|-------|----------|-------------|
| Launch Instance | 3-5 min | Create key, SG, launch bare-metal EC2, wait for running |
| List Instances | ~5s | Verify instance visible in VPC |
| SSH/GPU/Host OS | ~30s | SSH connectivity, GPU, kernel, drivers |
| Reboot Instance | 10-20 min | Reboot via API, wait for status checks, SSH |
| NIM Deploy | 5-15 min | Pull + start NIM container |
| NIM Validation | ~30s | Health, models, inference |
| Teardown | 15-25 min | Terminate bare-metal instance, delete resources |
| **Total** | **35-70 min** | Full test cycle |

## Cost & Cleanup

> **Warning**: These tests create AWS resources (EC2 bare-metal instances,
> security groups, key pairs) that incur costs. Bare-metal instances are
> significantly more expensive than regular VMs.
>
> Resources are automatically cleaned up during the teardown phase, but if
> teardown fails or is skipped, you must manually delete them to avoid
> ongoing charges.

| Resource | Hourly Cost (approx) |
|----------|---------------------|
| g4dn.metal | $7.82 |
| g5g.metal | $2.74 |

### Checking for Orphaned Resources

```bash
# Find instances tagged by isvtest
aws ec2 describe-instances \
  --filters "Name=tag:CreatedBy,Values=isvtest" "Name=instance-state-name,Values=running,stopped" \
  --query 'Reservations[*].Instances[*].[InstanceId,InstanceType,State.Name,Tags[?Key==`Name`].Value|[0]]' \
  --output table

# Terminate orphaned instances
aws ec2 terminate-instances --instance-ids i-xxx

# Find orphaned security groups
aws ec2 describe-security-groups \
  --filters "Name=group-name,Values=isv-bm-*" \
  --query 'SecurityGroups[*].[GroupId,GroupName]' --output table

# Delete orphaned security groups
aws ec2 delete-security-group --group-id sg-xxx

# Delete orphaned key pairs
aws ec2 describe-key-pairs --filters "Name=key-name,Values=isv-bm-*" --output table
aws ec2 delete-key-pair --key-name isv-bm-test-key
```

## Related Documentation

- [AWS VM Validation Guide](../../vm/docs/aws-vm.md) - VM-as-a-Service tests
- [AWS ISO Import Validation Guide](../../iso/docs/aws-iso.md) - VMDK/VHD import tests
- [AWS EKS Validation Guide](../../eks/docs/aws-eks.md) - Kubernetes cluster tests
- [AWS Network Validation Guide](../../network/docs/aws-network.md) - VPC and network tests
- [Configuration Guide](../../../../../docs/guides/configuration.md) - Config file options
- [isvctl Documentation](../../../../../docs/packages/isvctl.md) - CLI reference
