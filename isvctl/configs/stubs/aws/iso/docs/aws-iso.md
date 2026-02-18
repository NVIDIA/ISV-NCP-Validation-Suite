# AWS ISO/VMDK Import Validation Guide

This guide provides a complete walkthrough for validating AWS VM Import capabilities using the ISV validation framework. These tests verify the ability to import external disk images (VMDK) as AMIs and validate GPU functionality on the resulting instances.

## Overview

The AWS ISO/VMDK import validation tests verify:

1. **upload_image** - Download VMDK, upload to S3, import as AMI
2. **launch_instance** - Launch GPU instance from imported AMI
3. **teardown** - Clean up all resources (instance, AMI, S3, IAM roles)

**Key Features:**

- All steps are **SELF-CONTAINED** - they create their own S3 buckets, IAM roles, and clean up after
- **No pre-existing infrastructure required** - just AWS credentials
- Supports **local VMDK files** to skip download (faster iteration)
- **SSH validation** for GPU checks via paramiko
- **Step-based architecture** - scripts handle AWS operations, validations are platform-agnostic

## Architecture

### New Step-Based Architecture

```text
┌────────────────────────────────────────────────────────────────────┐
│  Scripts (Platform-Specific - boto3)                               │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐    │
│  │  upload_image.py │ │ launch_instance  │ │   teardown.py    │    │
│  │                  │ │       .py        │ │                  │    │
│  │ - Download VMDK  │ │ - Create keypair │ │ - Terminate EC2  │    │
│  │ - Upload to S3   │ │ - Create SG      │ │ - Delete AMI     │    │
│  │ - Import as AMI  │ │ - Launch EC2     │ │ - Delete bucket  │    │
│  │ - Output JSON    │ │ - Output JSON    │ │ - Cleanup IAM    │    │
│  └──────────────────┘ └──────────────────┘ └──────────────────┘    │
└────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────┐
│  Validations (Platform-Agnostic)                                   │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐    │
│  │ StepSuccessCheck │ │  SshGpuCheck     │ │ InstanceState    │    │
│  │ FieldExistsCheck │ │  SshOsCheck      │ │     Check        │    │
│  │ FieldValueCheck  │ │  SshConnectivity │ │                  │    │
│  └──────────────────┘ └──────────────────┘ └──────────────────┘    │
└────────────────────────────────────────────────────────────────────┘
```

### Test Flow

```text
┌─────────────────────────────────────────────────────────────────────┐
│  uv run isvctl test run -f isvctl/configs/aws-iso.yaml              │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────┐
│  1. upload_image (SETUP phase)                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Download VMDK ─▶ Create S3 Bucket ─▶ Upload ─▶ Import AMI   │   │
│  │ (or use local)   (isv-iso-xxx)       to S3    via VM Import │   │
│  │                                                             │   │
│  │ Output: {image_id, storage_bucket, disk_ids, ...}           │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                    │
│  Validations: StepSuccessCheck, FieldExistsCheck                   │
└────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────┐
│  2. launch_instance (SETUP phase)                                  │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Create Key Pair ─▶ Create SG ─▶ Launch g4dn.xlarge          │   │
│  │                                  from imported AMI          │   │
│  │                                                             │   │
│  │ Output: {instance_id, public_ip, key_path, ...}             │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                    │
│  Validations: InstanceStateCheck, SshConnectivityCheck,            │
│               SshGpuCheck, SshOsCheck                              │
└────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────┐
│  3. teardown (TEARDOWN phase)                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Terminate Instance ─▶ Delete AMI ─▶ Delete Snapshots        │   │
│  │ Delete Bucket ─▶ Delete Key Pair ─▶ Delete SG ─▶ Delete IAM │   │
│  │                                                             │   │
│  │ Output: {deleted: {instance, ami, bucket, ...}}             │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                    │
│  Validations: StepSuccessCheck                                     │
└────────────────────────────────────────────────────────────────────┘
```

## Prerequisites

### Required Tools

```bash
# AWS CLI (v2)
aws --version

# Python with boto3 and requests (installed via uv sync)
uv run python -c "import boto3, requests, paramiko; print('OK')"

# uv (Python package manager)
uv --version
```

### AWS Credentials

Configure AWS credentials with required permissions:

```bash
# Option 1: AWS CLI configuration
aws configure

# Option 2: Environment variables
export AWS_ACCESS_KEY_ID=AKIA...
export AWS_SECRET_ACCESS_KEY=...
export AWS_REGION=us-west-2

# Option 3: IAM instance role (recommended for CI/CD on EC2)
# Credentials are automatically provided by the instance metadata service
```

### Required IAM Permissions

The AWS credentials must have these permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:ImportImage",
        "ec2:DescribeImportImageTasks",
        "ec2:CancelImportTask",
        "ec2:RunInstances",
        "ec2:TerminateInstances",
        "ec2:DescribeInstances",
        "ec2:DescribeImages",
        "ec2:DeregisterImage",
        "ec2:DeleteSnapshot",
        "ec2:DescribeSnapshots",
        "ec2:CreateKeyPair",
        "ec2:DeleteKeyPair",
        "ec2:CreateSecurityGroup",
        "ec2:DeleteSecurityGroup",
        "ec2:AuthorizeSecurityGroupIngress",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeVpcs",
        "ec2:DescribeSubnets",
        "ec2:DescribeInstanceTypeOfferings",
        "ec2:CreateTags",
        "s3:CreateBucket",
        "s3:DeleteBucket",
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject",
        "s3:ListBucket",
        "s3:GetBucketLocation",
        "iam:CreateRole",
        "iam:DeleteRole",
        "iam:GetRole",
        "iam:PutRolePolicy",
        "iam:DeleteRolePolicy",
        "iam:AttachRolePolicy",
        "iam:DetachRolePolicy",
        "iam:CreateInstanceProfile",
        "iam:DeleteInstanceProfile",
        "iam:AddRoleToInstanceProfile",
        "iam:RemoveRoleFromInstanceProfile",
        "iam:PassRole"
      ],
      "Resource": "*"
    }
  ]
}
```

---

## Quick Start

```bash
# Clone and install
git clone <repository-url>
cd ISV-NCP-Validation-Suite
uv sync

# Run AWS ISO import validation
uv run isvctl test run -f isvctl/configs/aws-iso.yaml
```

### Test Duration Summary

| Phase | Duration | Description |
|-------|----------|-------------|
| Download VMDK | 2-5 min | ~700MB from Ubuntu cloud |
| Upload to S3 | 2-5 min | Depends on network speed |
| VM Import | 15-30 min | AWS import_image processing |
| Launch Instance | 5-8 min | Instance + status checks |
| GPU Validation | 1-2 min | SSH + nvidia-smi |
| Cleanup | 1-2 min | Delete all resources |
| **Total** | **25-50 min** | Full test cycle |

---

## Configuration

### aws-iso.yaml Structure

```yaml
version: "1.0"

commands:
  iso:
    phases: ["setup", "test", "teardown"]
    steps:
      # Step 1: Upload VMDK and import as AMI
      - name: upload_image
        phase: setup
        command: "python3 ./stubs/aws/iso/upload_image.py"
        args:
          - "--image-url"
          - "{{image_url}}"
          - "--image-format"
          - "{{image_format}}"
          - "--region"
          - "{{region}}"
        timeout: 3600

      # Step 2: Launch GPU instance from imported AMI
      - name: launch_instance
        phase: test
        command: "python3 ./stubs/aws/iso/launch_instance.py"
        args:
          - "--ami-id"
          - "{{steps.upload_image.image_id}}"  # Use generic field name
          - "--instance-type"
          - "{{instance_type}}"
          - "--region"
          - "{{region}}"
        timeout: 600

      # Step 3: Cleanup all resources
      - name: teardown
        phase: teardown
        command: "python3 ./stubs/aws/iso/teardown.py"
        args:
          - "--instance-id"
          - "{{steps.launch_instance.instance_id}}"
          - "--ami-id"
          - "{{steps.upload_image.image_id}}"  # Use generic field name
          - "--snapshot-ids"
          - "{{steps.upload_image.disk_ids | join(',')}}"  # Use generic field name
          - "--bucket-name"
          - "{{steps.upload_image.storage_bucket}}"  # Use generic field name
          # ... other cleanup args
        timeout: 300

tests:
  platform: iso
  cluster_name: "aws-iso-validation"

  settings:
    region: "us-west-2"
    image_url: "https://cloud-images.ubuntu.com/releases/noble/release/ubuntu-24.04-server-cloudimg-amd64.vmdk"
    image_format: "vmdk"
    instance_type: "g4dn.xlarge"

  validations:
    iso_import:
      step: upload_image
      checks:
        - StepSuccessCheck: {}
        - FieldExistsCheck:
            fields: ["image_id", "storage_bucket", "disk_ids"]

    instance_launch:
      step: launch_instance
      checks:
        - StepSuccessCheck: {}
        - InstanceStateCheck:
            expected_state: "running"

    ssh:
      step: launch_instance
      checks:
        - SshConnectivityCheck: {}
        - SshOsCheck:
            expected_os: "ubuntu"

    gpu:
      step: launch_instance
      checks:
        - SshGpuCheck:
            expected_gpus: 1

    teardown_checks:
      step: teardown
      checks:
        - StepSuccessCheck: {}
```

### Settings Reference

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `region` | string | `us-west-2` | AWS region |
| `image_url` | string | Ubuntu 24.04 | URL to download VMDK |
| `image_format` | string | `vmdk` | Image format (vmdk, vhd, ova, raw) |
| `instance_type` | string | `g4dn.xlarge` | GPU instance type |
| `teardown_flag` | string | `` | Set to `--skip-destroy` to skip cleanup |

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AWS_REGION` | AWS region for tests | `us-west-2` |
| `AWS_ACCESS_KEY_ID` | AWS access key | From AWS config |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key | From AWS config |
| `AWS_ISO_SKIP_TEARDOWN` | Skip teardown if `true` | `false` |

---

## Running Tests

### Run Full ISO Import Test

```bash
uv run isvctl test run -f isvctl/configs/aws-iso.yaml
```

### Skip Teardown (for debugging)

```bash
AWS_ISO_SKIP_TEARDOWN=true uv run isvctl test run -f isvctl/configs/aws-iso.yaml
```

### Run in Different Region

```bash
uv run isvctl test run -f isvctl/configs/aws-iso.yaml \
  --set tests.settings.region=us-east-1
```

### Use Different Instance Type

```bash
uv run isvctl test run -f isvctl/configs/aws-iso.yaml \
  --set tests.settings.instance_type=g5.xlarge
```

### Verbose Output

```bash
uv run isvctl test run -f isvctl/configs/aws-iso.yaml -v
```

---

## Validations

### Generic Validations Used

| Validation | Purpose | From Step |
|------------|---------|-----------|
| `StepSuccessCheck` | Verify step completed successfully | All steps |
| `FieldExistsCheck` | Verify required output fields exist | upload_image, launch_instance |
| `FieldValueCheck` | Verify specific field values | upload_image |
| `InstanceStateCheck` | Verify EC2 instance state | launch_instance |
| `SshConnectivityCheck` | Verify SSH access works | launch_instance |
| `SshOsCheck` | Verify OS type | launch_instance |
| `SshGpuCheck` | Verify GPU via nvidia-smi | launch_instance |
| `SshGpuStressCheck` | Run GPU stress test (optional) | launch_instance |

### Validation Timing

- **Default (no `phase`)**: Runs after setup steps complete
- **`phase: teardown`**: Runs after teardown steps complete

---

## Cleanup

Tests automatically clean up all resources, even on failure:

| Resource | Cleanup Action |
|----------|----------------|
| EC2 Instance | `terminate_instances()` |
| AMI | `deregister_image()` |
| EBS Snapshots | `delete_snapshot()` |
| S3 Objects | `delete_object()` |
| S3 Bucket | `delete_bucket()` |
| EC2 Key Pair | `delete_key_pair()` |
| Security Group | `delete_security_group()` |
| IAM Instance Profile | `delete_instance_profile()` |
| IAM Role | `delete_role()` |
| vmimport Role | Policy updated (not deleted) |

### Manual Cleanup

If cleanup fails, manually delete resources:

```bash
# Find orphaned resources
aws ec2 describe-instances --filters "Name=tag:Purpose,Values=isv-validation"
aws ec2 describe-images --owners self
aws s3 ls | grep isv-iso

# Manual cleanup
aws ec2 terminate-instances --instance-ids i-xxxxx
aws ec2 deregister-image --image-id ami-xxxxx
aws s3 rb s3://isv-iso-import-xxxxx --force
```

---

## Troubleshooting

### "Import task failed"

Check the import task status:

```bash
aws ec2 describe-import-image-tasks --import-task-ids import-ami-xxxxx
```

Common causes:

- VMDK format not supported (must be streamOptimized or flat)
- vmimport role missing permissions
- S3 bucket in different region

### "InsufficientInstanceCapacity"

No capacity for the instance type in the AZ. Try a different region or instance type:

```bash
uv run isvctl test run -f isvctl/configs/aws-iso.yaml \
  --set tests.settings.instance_type=g5.xlarge
```

### "SSH connection failed"

The instance may not have a public IP or security group is misconfigured:

```bash
# Check instance
aws ec2 describe-instances --instance-ids i-xxxxx

# Check security group
aws ec2 describe-security-groups --group-ids sg-xxxxx
```

### "nvidia-smi not found"

The imported AMI may not have NVIDIA drivers pre-installed. Consider:

1. Using an AMI with pre-installed NVIDIA drivers
2. Adding a step to install drivers after launch

---

## Supported Image Formats

| Format | Extension | Notes |
|--------|-----------|-------|
| VMDK | `.vmdk` | VMware virtual disk (recommended) |
| VHD | `.vhd` | Hyper-V virtual disk |
| OVA | `.ova` | Open Virtual Appliance |
| RAW | `.raw` | Raw disk image |

**Note**: QCOW2 is not directly supported by AWS VM Import. Convert to RAW first:

```bash
qemu-img convert -f qcow2 -O raw image.qcow2 image.raw
```

---

## Related Documentation

- [AWS VM Validation Guide](../../vm/docs/aws-vm.md) - EC2 GPU instance tests
- [AWS Network Validation Guide](../../network/docs/aws-network.md) - VPC and network tests
- [Configuration Guide](../../../../../docs/guides/configuration.md) - Config file options
- [isvctl Documentation](../../../../../docs/packages/isvctl.md) - CLI reference
