# AWS VM (VM-as-a-Service) Validation Guide

This guide provides a walkthrough for validating AWS EC2 VM-as-a-Service capabilities using the ISV validation framework.

## Overview

The AWS VM validation tests verify:

1. **Instance Lifecycle** - Instance provisioning, state verification
2. **SSH Access** - Remote configuration access via SSH
3. **Host OS Validation** - OS image and driver checks
4. **GPU Tests** - GPU visibility, stress workloads
5. **vCPU Pinning** - vCPU count, NUMA topology, CPU-GPU locality
6. **PCI Bus Config** - PCIe link speed/width, IOMMU groups, BAR memory
7. **Host Software Stack** - Linux kernel, libvirt/QEMU, SBIOS, NVIDIA drivers
8. **Reboot Resilience** - Instance reboot, recovery, full host OS persistence

## Architecture

### Step-Based Architecture

```text
┌────────────────────────────────────────────────────────────────────────────────────┐
│  Scripts (AWS-Specific - boto3)                                                    │
│  ┌──────────────────────────┐ ┌──────────────────────────┐ ┌────────────────────┐  │
│  │   launch_instance.py     │ │   reboot_instance.py     │ │   teardown.py      │  │
│  │                          │ │                          │ │                    │  │
│  │ - Find GPU AMI           │ │ - Verify running         │ │ - Terminate inst.  │  │
│  │ - Create key pair        │ │ - Capture pre-uptime     │ │ - Delete key pair  │  │
│  │ - Create security group  │ │ - Reboot via EC2 API     │ │ - Delete sec. grp  │  │
│  │ - Launch EC2 instance    │ │ - Wait for status OK     │ │ - Output JSON      │  │
│  │ - Wait for running       │ │ - Wait for SSH           │ │                    │  │
│  │ - Output JSON            │ │ - Confirm uptime reset   │ │                    │  │
│  │                          │ │ - Output JSON            │ │                    │  │
│  └──────────────────────────┘ └──────────────────────────┘ └────────────────────┘  │
│  ┌──────────────────────────┐                                                      │
│  │   list_instances.py      │                                                      │
│  │                          │                                                      │
│  │ - Filter by VPC ID       │                                                      │
│  │ - Verify target instance │                                                      │
│  │ - Output JSON            │                                                      │
│  └──────────────────────────┘                                                      │
└────────────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────────────────┐
│  Validations (Platform-Agnostic)                                                   │
│                                                                                    │
│  Instance          SSH / OS           GPU                Host OS                   │
│  ┌───────────────┐  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐  │
│  │ InstanceState │  │SshConnectiv. │  │ SshGpuCheck  │  │ SshVcpuPinningCheck   │  │
│  │    Check      │  │    Check     │  │              │  │ SshPciBusCheck        │  │
│  │ InstanceReboot│  │ SshOsCheck   │  │ SshGpuStress │  │ SshHostSoftwareCheck  │  │
│  │    Check      │  │              │  │    Check     │  │  (kernel, libvirt,    │  │
│  │ InstanceList  │  │              │  │              │  │   SBIOS, drivers)     │  │
│  │    Check      │  │              │  │              │  │                       │  │
│  │ StepSuccess   │  │              │  │              │  │                       │  │
│  │    Check      │  │              │  │              │  │                       │  │
│  └───────────────┘  └──────────────┘  └──────────────┘  └───────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────────────┘
```

### Test Flow

```text
┌───────────────────────────────────────────────────────────────────┐
│  uv run isvctl test run -f isvctl/configs/aws-vm.yaml             │
└───────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────┐
│  1. launch_instance (SETUP phase)                                  │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Find GPU AMI ─▶ Create Key Pair ─▶ Create SG ─▶ Launch EC2  │   │
│  │                                                             │   │
│  │ Output: {instance_id, public_ip, key_file, state, ...}      │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                    │
│  Validations: InstanceStateCheck, SshConnectivityCheck, SshOsCheck,│
│               SshGpuCheck, SshVcpuPinningCheck, SshPciBusCheck,    │
│               SshHostSoftwareCheck, SshGpuStressCheck              │
└────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────┐
│  2. list_instances (SETUP phase)                                   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Filter by VPC ID ─▶ Verify target instance in list          │   │
│  │                                                             │   │
│  │ Output: {instances, count, found_target, target_instance}   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                    │
│  Validations: InstanceListCheck                                    │
└────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────┐
│  3. reboot_instance (SETUP phase)                                  │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Verify Running ─▶ Reboot EC2 API ─▶ Wait Status OK ─▶ SSH   │   │
│  │                                                             │   │
│  │ Output: {instance_id, state, ssh_ready, uptime_seconds,     │   │
│  │          reboot_confirmed, ...}                             │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                    │
│  Validations: InstanceRebootCheck, InstanceStateCheck,             │
│               SshConnectivityCheck, SshOsCheck, SshGpuCheck,       │
│               SshVcpuPinningCheck, SshPciBusCheck,                 │
│               SshHostSoftwareCheck                                 │
└────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────┐
│  4. teardown (TEARDOWN phase)                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Terminate Instance ─▶ Delete Key Pair ─▶ Delete SG          │   │
│  │                                                             │   │
│  │ Output: {success, deleted: {instances, key_pairs, ...}}     │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                    │
│  Validations: StepSuccessCheck                                     │
└────────────────────────────────────────────────────────────────────┘
```

## Prerequisites

### Required Tools

- AWS CLI v2 (`aws`)
- Python 3.12+ with boto3, paramiko
- uv package manager

```bash
# Verify installation
aws --version
uv run python -c "import boto3, paramiko; print('OK')"
```

### AWS Credentials

```bash
# Option 1: IAM User credentials
export AWS_ACCESS_KEY_ID=AKIA...
export AWS_SECRET_ACCESS_KEY=...
export AWS_REGION=us-west-2

# Option 2: STS temporary credentials (recommended)
export AWS_ACCESS_KEY_ID=ASIA...
export AWS_SECRET_ACCESS_KEY=...
export AWS_SESSION_TOKEN=...
export AWS_REGION=us-west-2
```

### Required IAM Permissions

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:RunInstances", "ec2:TerminateInstances", "ec2:DescribeInstances",
        "ec2:DescribeInstanceStatus", "ec2:RebootInstances",
        "ec2:CreateKeyPair", "ec2:DeleteKeyPair", "ec2:DescribeKeyPairs",
        "ec2:CreateSecurityGroup", "ec2:DeleteSecurityGroup",
        "ec2:AuthorizeSecurityGroupIngress", "ec2:DescribeSecurityGroups",
        "ec2:DescribeVpcs", "ec2:DescribeSubnets",
        "ec2:CreateTags", "ec2:DescribeImages", "ec2:DescribeAvailabilityZones",
        "ec2:DescribeInstanceTypeOfferings",
        "sts:GetCallerIdentity"
      ],
      "Resource": "*"
    }
  ]
}
```

---

## Quick Start

### 1. Install Dependencies

```bash
cd ISV-NCP-Validation-Suite
uv sync
```

### 2. Configure AWS Credentials

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_REGION=us-west-2
```

### 3. Run Tests

```bash
# Run all tests - instance auto-provisioned
uv run isvctl test run -f isvctl/configs/aws-vm.yaml

# Verbose output
uv run isvctl test run -f isvctl/configs/aws-vm.yaml -v
```

### 4. Run Specific Tests

```bash
# Run only SSH tests
uv run isvctl test run -f isvctl/configs/aws-vm.yaml -- -k "Ssh"

# Run only GPU tests
uv run isvctl test run -f isvctl/configs/aws-vm.yaml -- -m "gpu"

# Run only host OS checks (vCPU pinning, PCI bus, software stack)
uv run isvctl test run -f isvctl/configs/aws-vm.yaml -- -k "Vcpu or PciBus or HostSoftware"

# Run only reboot validations
uv run isvctl test run -f isvctl/configs/aws-vm.yaml -- -k "reboot"

# Exclude workload tests (stress tests)
uv run isvctl test run -f isvctl/configs/aws-vm.yaml -- -m "not workload"
```

See the [Validation Details](#validation-details) section below for full usage docs on each check.

---

## Configuration

### aws-vm.yaml Structure

```yaml
version: "1.0"

commands:
  vm:
    phases: ["setup", "teardown"]
    steps:
      # Step 1: Launch EC2 GPU instance
      - name: launch_instance
        phase: setup
        command: "python3 ./stubs/aws/vm/launch_instance.py"
        args:
          - "--name"
          - "isv-test-gpu"
          - "--instance-type"
          - "{{instance_type}}"
          - "--region"
          - "{{region}}"
        timeout: 600

      # Step 2: List instances in VPC and verify target
      - name: list_instances
        phase: setup
        command: "python3 ./stubs/aws/vm/list_instances.py"
        args:
          - "--vpc-id"
          - "{{steps.launch_instance.vpc_id}}"
          - "--instance-id"
          - "{{steps.launch_instance.instance_id}}"
          - "--region"
          - "{{region}}"
        timeout: 120

      # Step 3: Reboot instance and validate recovery
      - name: reboot_instance
        phase: setup
        command: "python3 ./stubs/aws/vm/reboot_instance.py"
        args:
          - "--instance-id"
          - "{{steps.launch_instance.instance_id}}"
          - "--region"
          - "{{region}}"
          - "--key-file"
          - "{{steps.launch_instance.key_file}}"
          - "--public-ip"
          - "{{steps.launch_instance.public_ip}}"
        timeout: 600

      # Step 4: Teardown resources
      - name: teardown
        phase: teardown
        command: "python3 ./stubs/aws/vm/teardown.py"
        args:
          - "--instance-id"
          - "{{steps.launch_instance.instance_id}}"
          - "--delete-key-pair"
          - "--delete-security-group"
        timeout: 600

tests:
  platform: vm
  cluster_name: "aws-vm-validation"

  settings:
    region: "us-west-2"
    instance_type: "g5.xlarge"

  validations:
    setup_checks:
      step: launch_instance
      checks:
        - InstanceStateCheck:
            expected_state: "running"

    list_instances:
      step: list_instances
      checks:
        - InstanceListCheck:
            min_count: 1

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

    host_os:
      step: launch_instance
      checks:
        - SshVcpuPinningCheck: {}
        - SshPciBusCheck:
            expected_gpus: 1
        - SshHostSoftwareCheck: {}

    gpu_workload:
      step: launch_instance
      checks:
        - SshGpuStressCheck:
            duration: 60

    # Reboot validations
    reboot_checks:
      step: reboot_instance
      checks:
        - InstanceRebootCheck:
            max_uptime: 600

    reboot_state:
      step: reboot_instance
      checks:
        - InstanceStateCheck:
            expected_state: "running"

    reboot_ssh:
      step: reboot_instance
      checks:
        - SshConnectivityCheck: {}
        - SshOsCheck:
            expected_os: "ubuntu"

    reboot_gpu:
      step: reboot_instance
      checks:
        - SshGpuCheck:
            expected_gpus: 1

    reboot_host_os:
      step: reboot_instance
      checks:
        - SshVcpuPinningCheck: {}
        - SshPciBusCheck:
            expected_gpus: 1
        - SshHostSoftwareCheck: {}

    teardown_checks:
      step: teardown
      checks:
        - StepSuccessCheck: {}

  exclude:
    markers:
      - workload  # Exclude stress test by default
```

### Settings Reference

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `region` | string | `us-west-2` | AWS region |
| `instance_type` | string | `g5.xlarge` | GPU instance type |

### Instance Type to GPU Count

| Instance Type | GPUs | GPU Type |
|---------------|------|----------|
| g5.xlarge | 1 | A10G |
| g5.2xlarge | 1 | A10G |
| g5.12xlarge | 4 | A10G |
| g5.48xlarge | 8 | A10G |
| g4dn.xlarge | 1 | T4 |
| p4d.24xlarge | 8 | A100 |

---

## Validations

### Validation Types

| Validation | Category | Description |
|------------|----------|-------------|
| `InstanceStateCheck` | setup_checks, reboot_state | Verify instance is in expected state (running) |
| `InstanceListCheck` | list_instances | Verify instances exist in VPC and target instance is present |
| `SshConnectivityCheck` | ssh, reboot_ssh | Test SSH connectivity and command execution |
| `SshOsCheck` | ssh, reboot_ssh | Verify OS type (ubuntu, etc.) |
| `SshGpuCheck` | gpu, reboot_gpu | Verify GPU visibility via nvidia-smi |
| `SshVcpuPinningCheck` | host_os, reboot_host_os | Verify vCPU count, online status, NUMA topology, CPU affinity, GPU-NUMA locality |
| `SshPciBusCheck` | host_os, reboot_host_os | Verify PCI GPU enumeration, PCIe link speed/width, IOMMU groups, BAR memory, ACS |
| `SshHostSoftwareCheck` | host_os, reboot_host_os | Verify Linux kernel, libvirt/QEMU/KVM, SBIOS (vendor/version/date), NVIDIA driver |
| `SshGpuStressCheck` | gpu_workload | Run GPU stress test (excluded by default) |
| `InstanceRebootCheck` | reboot_checks | Verify reboot succeeded: API call, state recovery, SSH restored, uptime reset |
| `StepSuccessCheck` | teardown_checks | Verify teardown completed successfully |

### Validation Details

Each validation SSHs into the host and runs a series of subtests. All checks report
subtest-level results so you can pinpoint exactly what passed or failed.

---

#### SshVcpuPinningCheck

Validates that vCPUs are correctly provisioned, online, and topologically sane.

**Subtests:**

| Subtest | What it checks |
|---------|---------------|
| `vcpu_count` | vCPU count from `nproc` matches `expected_vcpus` (if set) |
| `vcpu_online` | All vCPUs are online (`/sys/devices/system/cpu/online`) |
| `cpu_affinity` | CPU affinity mask of PID 1 (should span all vCPUs) |
| `numa_topology` | All NUMA nodes have CPUs assigned, no empty nodes |
| `numa_node{N}` | Per-node detail: which CPUs, how many cores |
| `gpu{N}_numa` | GPU PCI device NUMA node (GPU-CPU locality) |

**Config parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `expected_vcpus` | int | *(auto-detect)* | Fail if vCPU count doesn't match |

**Usage examples:**

```yaml
# Auto-detect (report what's found)
- SshVcpuPinningCheck: {}

# Enforce 4 vCPUs (for g5.xlarge)
- SshVcpuPinningCheck:
    expected_vcpus: 4

# Enforce 16 vCPUs (for g5.4xlarge)
- SshVcpuPinningCheck:
    expected_vcpus: 16
```

**Sample output:**

```text
[PASS] vcpu_count      : 4 vCPUs
[PASS] vcpu_online     : Online: 0-3 (4/4)
[PASS] cpu_affinity    : pid 1's current affinity mask: f
[PASS] numa_topology   : 1 NUMA node(s), all populated: True
[PASS] numa_node0      : node0: CPUs 0-3 (4 cores)
[PASS] gpu0_numa       : GPU 0 (00000000:00:1E.0) -> NUMA node 0
```

---

#### SshPciBusCheck

Validates that the PCI bus is correctly configured for GPU passthrough.

**Subtests:**

| Subtest | What it checks |
|---------|---------------|
| `pci_gpu_count` | NVIDIA GPU devices on PCI bus (`lspci`) match expected count |
| `pci_dev_{N}` | Per-device BDF address and description |
| `pcie_link_gpu{N}` | PCIe generation (current/max) and link width (current/max) |
| `iommu_groups` | IOMMU group assignment for GPU devices |
| `gpu{N}_bar_mem` | GPU BAR memory region mapped correctly |
| `acs` | PCI Access Control Services status |

**Config parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `expected_gpus` | int | `1` | Expected number of GPU PCI devices |
| `expected_link_width` | string | *(none)* | Expected PCIe link width, e.g. `"x16"` |

**Usage examples:**

```yaml
# Default (1 GPU, report link info)
- SshPciBusCheck:
    expected_gpus: 1

# Multi-GPU instance, enforce x16 link
- SshPciBusCheck:
    expected_gpus: 4
    expected_link_width: "x16"
```

**Sample output:**

```text
[PASS] pci_gpu_count    : 1 GPU PCI device(s) (expected 1)
[PASS] pci_dev_0        : 00:1e.0: 3D controller: NVIDIA Corporation GA102GL [A10G]
[PASS] pcie_link_gpu0   : GPU 0: Gen4/4, x16/x16
[PASS] iommu_groups     : 0000:00:1e.0 -> IOMMU group 17
[PASS] gpu0_bar_mem     : GPU 0 (00:1E.0): 23028 MiB
[PASS] acs              : ACS info not available (OK for cloud VMs)
```

---

#### SshHostSoftwareCheck

Validates the full software stack: Linux kernel, libvirt/QEMU, System BIOS, and NVIDIA drivers.

**Subtests:**

| Subtest | Category | What it checks |
|---------|----------|---------------|
| `kernel_version` | Kernel | `uname -r`, optionally matches expected version |
| `kernel_build` | Kernel | Kernel build string (`uname -v`) |
| `kernel_modules` | Kernel | GPU/virt modules loaded: `nvidia`, `kvm`, `vfio`, `vhost` |
| `libvirt` | Virtualization | `libvirtd --version`, optionally matches expected |
| `qemu` | Virtualization | QEMU/qemu-kvm version |
| `kvm` | Virtualization | `/dev/kvm` hardware virtualization support |
| `virsh` | Virtualization | `virsh version --daemon` hypervisor API |
| `bios_vendor` | SBIOS | BIOS vendor via `dmidecode` / sysfs |
| `bios_version` | SBIOS | BIOS firmware version |
| `bios_date` | SBIOS | BIOS release date |
| `system_product` | SBIOS | System product / platform name |
| `boot_mode` | SBIOS | UEFI vs Legacy BIOS |
| `nvidia_driver` | NVIDIA | Driver version from `nvidia-smi` |
| `cuda_version` | NVIDIA | CUDA runtime version |
| `nvidia_module` | NVIDIA | Kernel module version (`/sys/module/nvidia/version`) |
| `nvidia_persistence` | NVIDIA | Persistence mode on/off |

**Config parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `expected_kernel` | string | *(none)* | Kernel version substring to enforce (e.g. `"6.5"`) |
| `expected_driver_version` | string | *(none)* | NVIDIA driver version substring (e.g. `"550"`) |
| `expected_libvirt_version` | string | *(none)* | libvirt version substring (e.g. `"10.0"`) |
| `expected_bios_vendor` | string | *(none)* | BIOS vendor name (e.g. `"Amazon"`, `"Dell"`) |

When no `expected_*` parameter is set, the check **reports** the value without failing.
When set, it **enforces** the value and fails if there's a mismatch.

**Usage examples:**

```yaml
# Report-only mode (discover what's installed)
- SshHostSoftwareCheck: {}

# Enforce specific versions
- SshHostSoftwareCheck:
    expected_kernel: "6.5"
    expected_driver_version: "550"

# Full enforcement (bare-metal / on-prem)
- SshHostSoftwareCheck:
    expected_kernel: "6.8"
    expected_driver_version: "550"
    expected_libvirt_version: "10.0"
    expected_bios_vendor: "Dell Inc."
```

**Sample output:**

```text
[PASS] kernel_version    : Kernel: 6.5.0-1024-aws
[PASS] kernel_build      : #24~22.04.1-Ubuntu SMP Wed May 1 15:38:15 UTC 2024
[PASS] kernel_modules    : Key modules: kvm, kvm_intel, nvidia, nvidia_drm, nvidia_modeset, nvidia_uvm
[PASS] libvirt           : libvirt not installed (OK for bare metal/cloud)
[PASS] qemu              : QEMU not installed (OK for bare metal/cloud)
[PASS] kvm               : KVM not available
[PASS] bios_vendor       : BIOS vendor: Amazon EC2
[PASS] bios_version      : BIOS version: 1.0
[PASS] bios_date         : BIOS date: 10/16/2017
[PASS] system_product    : Platform: c5.xlarge
[PASS] boot_mode         : Boot mode: UEFI
[PASS] nvidia_driver     : NVIDIA Driver: 550.54.15
[PASS] cuda_version      : CUDA: 12.4
[PASS] nvidia_module     : nvidia.ko: 550.54.15
[PASS] nvidia_persistence : Persistence mode: Enabled
```

---

#### InstanceRebootCheck

Validates that an EC2 instance rebooted successfully and fully recovered.

**Subtests (checked in order):**

| Check | Fails if |
|-------|----------|
| `reboot_initiated` | Reboot API call did not succeed |
| `state` | Instance is not `"running"` after reboot |
| `ssh_ready` | SSH connectivity not restored |
| `uptime_seconds` | Uptime exceeds `max_uptime` (reboot didn't happen) |
| `reboot_confirmed` | Pre/post uptime comparison shows no reset |

**Config parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_uptime` | int | `600` | Max uptime in seconds to consider reboot confirmed |

**Usage examples:**

```yaml
# Default (600s max uptime)
- InstanceRebootCheck: {}

# Stricter: reboot must result in <5 min uptime
- InstanceRebootCheck:
    max_uptime: 300
```

---

### Running Specific Validations

```bash
# Run all validations
uv run isvctl test run -f isvctl/configs/aws-vm.yaml

# Run only host OS checks (vCPU, PCI, software stack)
uv run isvctl test run -f isvctl/configs/aws-vm.yaml -- -k "Vcpu or PciBus or HostSoftware"

# Run only vCPU pinning
uv run isvctl test run -f isvctl/configs/aws-vm.yaml -- -k "VcpuPinning"

# Run only PCI bus checks
uv run isvctl test run -f isvctl/configs/aws-vm.yaml -- -k "PciBus"

# Run only host software stack (kernel, libvirt, SBIOS, driver)
uv run isvctl test run -f isvctl/configs/aws-vm.yaml -- -k "HostSoftware"

# Run only reboot validations
uv run isvctl test run -f isvctl/configs/aws-vm.yaml -- -k "reboot"

# Run only GPU checks
uv run isvctl test run -f isvctl/configs/aws-vm.yaml -- -m "gpu"

# Exclude stress tests
uv run isvctl test run -f isvctl/configs/aws-vm.yaml -- -m "not workload"

# Verbose output with full subtest details
uv run isvctl test run -f isvctl/configs/aws-vm.yaml -v -- -v -s
```

### Validation Timing

- **Default (no `phase`)**: Runs after setup steps complete
- **`phase: teardown`**: Runs after teardown steps complete

### Test Duration Summary

| Phase | Duration | Description |
|-------|----------|-------------|
| Launch Instance | 3-5 min | Create key, SG, launch EC2, wait for running |
| SSH Validation | ~30s | Connect and test commands |
| GPU Validation | ~30s | Run nvidia-smi |
| Host OS Checks | ~30-60s | vCPU pinning, PCI bus, kernel, libvirt, SBIOS, drivers |
| GPU Stress | ~1-2 min | GPU stress test (excluded by default) |
| Reboot Instance | 2-5 min | Reboot via API, wait for status checks, SSH |
| Reboot Validation | ~1-2 min | Verify state, SSH, GPU, host OS after reboot |
| Teardown | ~1 min | Terminate instance, delete resources |
| **Total** | **8-15 min** | Full test cycle |

---

## Script Outputs

### launch_instance.py Output

```json
{
  "success": true,
  "instance_id": "i-0abc123def456",
  "instance_type": "g5.xlarge",
  "public_ip": "54.1.2.3",
  "private_ip": "172.31.1.5",
  "state": "running",
  "ami_id": "ami-0abc123",
  "key_name": "isv-test-key-abc123",
  "key_path": "/home/user/.ssh/isv-test-key-abc123.pem",
  "security_group_id": "sg-0abc123",
  "ssh_user": "ubuntu"
}
```

### list_instances.py Output

```json
{
  "success": true,
  "platform": "vm",
  "instances": [
    {
      "instance_id": "i-0abc123def456",
      "instance_type": "g5.xlarge",
      "state": "running",
      "public_ip": "54.1.2.3",
      "private_ip": "172.31.1.5",
      "vpc_id": "vpc-0abc123"
    }
  ],
  "count": 1,
  "found_target": true,
  "target_instance": "i-0abc123def456"
}
```

**Key fields for validations:**

| Field | Type | Description |
|-------|------|-------------|
| `instances` | array | List of non-terminated instances in the VPC |
| `count` | int | Number of instances returned |
| `found_target` | bool | Whether the target instance ID was found in the list |
| `target_instance` | string | The instance ID that was searched for |

### reboot_instance.py Output

```json
{
  "success": true,
  "platform": "vm",
  "instance_id": "i-0abc123def456",
  "region": "us-west-2",
  "state": "running",
  "public_ip": "54.1.2.3",
  "private_ip": "172.31.1.5",
  "key_file": "/tmp/isv-test-key.pem",
  "ssh_user": "ubuntu",
  "reboot_initiated": true,
  "ssh_ready": true,
  "pre_reboot_uptime": 342.5,
  "uptime_seconds": 45.2,
  "reboot_confirmed": true
}
```

**Key fields for validations:**

| Field | Type | Description |
|-------|------|-------------|
| `reboot_initiated` | bool | EC2 reboot API call succeeded |
| `state` | string | Instance state after reboot (should be `"running"`) |
| `ssh_ready` | bool | SSH connectivity restored after reboot |
| `uptime_seconds` | float | System uptime after reboot (low = reboot confirmed) |
| `reboot_confirmed` | bool | Uptime comparison confirms reboot occurred |
| `pre_reboot_uptime` | float | System uptime before reboot (for comparison) |

### teardown.py Output

```json
{
  "success": true,
  "platform": "vm",
  "resources_destroyed": true,
  "deleted": {
    "instances": ["i-0abc123def456"],
    "security_groups": ["sg-0abc123"],
    "key_pairs": ["isv-test-key-abc123"]
  }
}
```

---

## Troubleshooting

### Instance Not Starting

```bash
# Check AWS limits
aws service-quotas list-service-quotas --service-code ec2 --region us-west-2

# Try smaller instance
uv run isvctl test run -f isvctl/configs/aws-vm.yaml \
  --set tests.settings.instance_type=g4dn.xlarge
```

### SSH Connection Failed

```bash
# Check if instance has public IP
aws ec2 describe-instances --instance-ids i-xxx \
  --query 'Reservations[*].Instances[*].PublicIpAddress'

# Check security group rules
aws ec2 describe-security-groups --group-ids sg-xxx

# Test SSH manually
ssh -i ~/.ssh/isv-test-key-xxx.pem ubuntu@<public-ip>
```

### Reboot Validation Failed

```bash
# Check instance state via AWS CLI
aws ec2 describe-instances --instance-ids i-xxx \
  --query 'Reservations[*].Instances[*].[State.Name]'

# Check instance status checks
aws ec2 describe-instance-status --instance-ids i-xxx \
  --query 'InstanceStatuses[*].[InstanceStatus.Status,SystemStatus.Status]'

# SSH in and check uptime manually
ssh -i ~/.ssh/isv-test-key-xxx.pem ubuntu@<public-ip> "cat /proc/uptime"

# Check system logs for reboot evidence
ssh -i ~/.ssh/isv-test-key-xxx.pem ubuntu@<public-ip> "last reboot | head -5"
```

### Host OS Check Failed (vCPU / PCI / Software)

```bash
# SSH into instance for manual inspection
ssh -i ~/.ssh/isv-test-key-xxx.pem ubuntu@<public-ip>

# --- vCPU Pinning ---
nproc                                         # vCPU count
cat /sys/devices/system/cpu/online            # Online CPUs
taskset -p 1                                  # CPU affinity of init
lscpu | grep NUMA                             # NUMA topology
nvidia-smi --query-gpu=index,gpu_bus_id --format=csv,noheader  # GPU bus IDs

# --- PCI Bus ---
lspci -d 10de: -nn                            # NVIDIA PCI devices
nvidia-smi -q -d PCIE                         # PCIe link details
find /sys/kernel/iommu_groups/ -type l        # IOMMU groups

# --- Kernel & Drivers ---
uname -r                                      # Kernel version
uname -v                                      # Kernel build
lsmod | grep -E 'nvidia|kvm|vfio'            # Key modules
nvidia-smi                                    # Driver + CUDA
cat /sys/module/nvidia/version                # Kernel module version

# --- libvirt / QEMU ---
libvirtd --version 2>/dev/null                # libvirt version
qemu-system-x86_64 --version 2>/dev/null     # QEMU version
test -c /dev/kvm && echo "KVM OK"            # KVM support

# --- SBIOS ---
sudo dmidecode -s bios-vendor                 # BIOS vendor
sudo dmidecode -s bios-version                # BIOS version
sudo dmidecode -s bios-release-date           # BIOS date
sudo dmidecode -s system-product-name         # Platform
test -d /sys/firmware/efi && echo "UEFI" || echo "Legacy"  # Boot mode
```

### GPU Not Detected

```bash
# SSH into instance
ssh -i ~/.ssh/isv-test-key-xxx.pem ubuntu@<public-ip>

# Check NVIDIA driver
nvidia-smi

# Check if using GPU AMI
lsmod | grep nvidia
```

### Cleanup Failed Resources

```bash
# List instances with ISV tags
aws ec2 describe-instances \
  --filters "Name=tag:Purpose,Values=isv-validation" \
  --query 'Reservations[*].Instances[*].[InstanceId,State.Name]'

# Terminate orphaned instances
aws ec2 terminate-instances --instance-ids i-xxx

# Delete orphaned security groups
aws ec2 delete-security-group --group-id sg-xxx

# Delete orphaned key pairs
aws ec2 delete-key-pair --key-name isv-test-key-xxx
```

---

## Cost Considerations

| Resource | Duration | Cost (approx) |
|----------|----------|---------------|
| g5.xlarge | 1 hour | $1.01 |
| g4dn.xlarge | 1 hour | $0.53 |
| t3.micro | 1 hour | $0.01 |

**Tip:** The teardown phase cleans up all resources automatically. Use `--skip-destroy` flag in teardown.py to keep resources for debugging.

---

## Related Documentation

- [AWS ISO Import Validation Guide](../../iso/docs/aws-iso.md) - VMDK/VHD import tests
- [AWS EKS Validation Guide](../../eks/docs/aws-eks.md) - Kubernetes cluster tests
- [AWS Network Validation Guide](../../network/docs/aws-network.md) - VPC and network tests
- [Configuration Guide](../../../../../docs/guides/configuration.md) - Config file options
- [isvctl Documentation](../../../../../docs/packages/isvctl.md) - CLI reference
