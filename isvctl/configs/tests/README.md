# Validation Test Suites

Provider-agnostic test suites for ISV Lab validation. Each YAML defines **what to test**; provider configs import them and supply **how** (platform-specific scripts).

For background on the step-based architecture, writing scripts, and running validations, see the [External Validation Guide](../../../docs/guides/external-validation-guide.md).

## Quick Start

```bash
# 1. Copy the test suites and stubs
cp -r isvctl/configs/tests/ isvctl/configs/my-isv/
cp -r isvctl/configs/stubs/ isvctl/configs/my-isv/stubs/

# 2. Implement the stub scripts for your platform
#    Each stub has a TODO block showing what to implement

# 3. Run
uv run isvctl test run -f isvctl/configs/my-isv/vm.yaml
```

Or use the **import directive** (recommended for providers):

```yaml
# isvctl/configs/providers/my-isv/vm.yaml
import: ../../tests/vm.yaml

commands:
  vm:
    steps:
      - name: launch_instance
        command: "python3 ../../stubs/my-isv/vm/launch_instance.py"
      # ... override only the commands, validations stay the same
```

## Available Test Suites

| Test Suite | Domain | Stubs | AWS Reference |
|------------|--------|-------|---------------|
| [`iam.yaml`](iam.yaml) | User lifecycle (create → verify → delete) | [`stubs/iam/`](../stubs/iam/) (3 scripts) | [`providers/aws/iam.yaml`](../providers/aws/iam.yaml) |
| [`network.yaml`](network.yaml) | VPC CRUD, subnets, isolation, security, connectivity, traffic, DDI, SDN | [`stubs/network/`](../stubs/network/) (15 scripts) | [`providers/aws/network.yaml`](../providers/aws/network.yaml) |
| [`vm.yaml`](vm.yaml) | GPU VM lifecycle: launch → tags → stop/start → reboot → NIM → teardown | [`stubs/vm/`](../stubs/vm/) (8 scripts) | [`providers/aws/vm.yaml`](../providers/aws/vm.yaml) |
| [`bare_metal.yaml`](bare_metal.yaml) | BMaaS lifecycle: launch → topology → serial → stop/start → reboot → NIM → teardown | [`stubs/bare_metal/`](../stubs/bare_metal/) (9 scripts) | [`providers/aws/bare_metal.yaml`](../providers/aws/bare_metal.yaml) |
| [`k8s.yaml`](k8s.yaml) | Kubernetes GPU cluster: nodes, GPU operator, scheduling, workloads | [`stubs/k8s/`](../stubs/k8s/) (2 scripts) | [`providers/aws/eks.yaml`](../providers/aws/eks.yaml) |
| [`slurm.yaml`](slurm.yaml) | Slurm HPC cluster: partitions, jobs, GPU allocation | [`stubs/slurm/`](../stubs/slurm/) (2 scripts) | — |
| [`control-plane.yaml`](control-plane.yaml) | API health, access key lifecycle, tenant lifecycle | [`stubs/control-plane/`](../stubs/control-plane/) (10 scripts) | [`providers/aws/control-plane.yaml`](../providers/aws/control-plane.yaml) |
| [`image-registry.yaml`](image-registry.yaml) | Image upload, CRUD, VM launch, install config, BMaaS provisioning | [`stubs/image-registry/`](../stubs/image-registry/) (7 scripts) | [`providers/aws/image-registry.yaml`](../providers/aws/image-registry.yaml) |

## Test Suite Details

### IAM (`iam.yaml`)

| Step | Phase | Script | Key JSON Fields |
|------|-------|--------|-----------------|
| `create_user` | setup | `stubs/iam/create_user.py` | `username`, `user_id`, `access_key_id`, `secret_access_key` |
| `test_credentials` | test | `stubs/iam/test_credentials.py` | `account_id`, `tests.identity.passed`, `tests.access.passed` |
| `teardown` | teardown | `stubs/iam/delete_user.py` | `resources_deleted`, `message` |

### Network (`network.yaml`)

| Step | Phase | Script | What It Tests |
|------|-------|--------|---------------|
| `create_network` | setup | `stubs/network/create_vpc.py` | Shared VPC creation |
| `vpc_crud` | test | `stubs/network/vpc_crud_test.py` | Create/Read/Update/Delete lifecycle |
| `subnet_config` | test | `stubs/network/subnet_test.py` | Multi-AZ subnet distribution |
| `vpc_isolation` | test | `stubs/network/isolation_test.py` | Security boundaries between VPCs |
| `security_blocking` | test | `stubs/network/security_test.py` | Firewall/ACL blocking rules |
| `connectivity_test` | test | `stubs/network/test_connectivity.py` | Instance network assignment |
| `traffic_validation` | test | `stubs/network/traffic_test.py` | Ping allowed/blocked, internet |
| `vpc_ip_config` | test | `stubs/network/vpc_ip_config_test.py` | DHCP options, subnet CIDRs, auto-assign IP |
| `dhcp_ip_test` | test | `stubs/network/dhcp_ip_test.py` | DHCP lease, IP match, DNS options via SSH |
| `byoip_test` | test | `stubs/network/byoip_test.py` | Bring-Your-Own-IP with custom CIDRs |
| `stable_ip_test` | test | `stubs/network/stable_ip_test.py` | IP persistence across stop/start |
| `floating_ip_test` | test | `stubs/network/floating_ip_test.py` | Atomic IP switch between instances |
| `dns_test` | test | `stubs/network/dns_test.py` | Custom internal domain resolution |
| `peering_test` | test | `stubs/network/peering_test.py` | Cross-VPC connectivity |
| `teardown` | teardown | `stubs/network/teardown.py` | VPC cleanup |

### VM (`vm.yaml`)

| Step | Phase | Script | Key JSON Fields |
|------|-------|--------|-----------------|
| `launch_instance` | setup | `stubs/vm/launch_instance.py` | `instance_id`, `public_ip`, `key_file`, `vpc_id` |
| `list_instances` | test | `stubs/vm/list_instances.py` | `instances`, `total_count` |
| `verify_tags` | test | `stubs/vm/describe_tags.py` | `instance_id`, `tags`, `tag_count` |
| `stop_instance` | test | `stubs/vm/stop_instance.py` | `instance_id`, `state`, `stop_initiated` |
| `start_instance` | test | `stubs/vm/start_instance.py` | `instance_id`, `state`, `public_ip`, `ssh_ready` |
| `reboot_instance` | test | `stubs/vm/reboot_instance.py` | `uptime_seconds`, `ssh_connectivity` |
| `serial_console` | test | `stubs/vm/serial_console.py` | `console_available`, `serial_access_enabled` |
| `deploy_nim` | test | `stubs/common/deploy_nim.py` | `container_id`, `health_endpoint` |
| `teardown_nim` | teardown | `stubs/common/teardown_nim.py` | `message` |
| `teardown` | teardown | `stubs/vm/teardown.py` | `resources_deleted`, `message` |

### Bare Metal (`bare_metal.yaml`)

| Step | Phase | Script | Key JSON Fields |
|------|-------|--------|-----------------|
| `launch_instance` | setup | `stubs/bare_metal/launch_instance.py` | `instance_id`, `public_ip`, `key_file`, `vpc_id` |
| `list_instances` | test | `stubs/vm/list_instances.py` | Reuses VM script |
| `topology_placement` | test | `stubs/bare_metal/topology_placement.py` | `placement_supported`, `operations` |
| `serial_console` | test | `stubs/bare_metal/serial_console.py` | `console_available`, `serial_access_enabled` |
| `stop_instance` | test | `stubs/bare_metal/stop_instance.py` | `instance_id`, `state`, `stop_initiated` |
| `start_instance` | test | `stubs/bare_metal/start_instance.py` | `instance_id`, `state`, `public_ip`, `ssh_ready` |
| `describe_instance` | test | `stubs/bare_metal/describe_instance.py` | `instance_state`, `public_ip`, `key_file` |
| `reboot_instance` | test | `stubs/bare_metal/reboot_instance.py` | `uptime_seconds`, `ssh_connectivity` |
| `reinstall_instance` | test | `stubs/bare_metal/reinstall_instance.py` | `instance_state` (skipped by default) |
| `deploy_nim` | test | `stubs/common/deploy_nim.py` | Shared NIM deployment |
| `teardown_nim` | teardown | `stubs/common/teardown_nim.py` | Shared NIM cleanup |
| `teardown` | teardown | `stubs/bare_metal/teardown.py` | `resources_deleted`, `message` |
| `verify_teardown` | teardown | `stubs/bare_metal/verify_terminated.py` | `checks.instance_terminated`, `checks.sg_deleted` |

### Kubernetes (`k8s.yaml`)

| Step | Phase | Script |
|------|-------|--------|
| `setup` | setup | `stubs/k8s/setup.sh` |
| `teardown` | teardown | `stubs/k8s/teardown.sh` |

Validations use `kubectl` directly: node counts, GPU operator, pod health, NCCL/NIM workloads.

### Slurm (`slurm.yaml`)

| Step | Phase | Script |
|------|-------|--------|
| `setup` | setup | `stubs/slurm/setup.sh` |
| `teardown` | teardown | `stubs/slurm/teardown.sh` |

Validations use `sinfo`/`srun` directly: partitions, GPU allocation, job scheduling.

### Control Plane (`control-plane.yaml`)

| Step | Phase | Script | Key JSON Fields |
|------|-------|--------|-----------------|
| `check_api` | setup | `stubs/control-plane/check_api.py` | `account_id`, `tests` |
| `create_access_key` | setup | `stubs/control-plane/create_access_key.py` | `username`, `access_key_id` |
| `create_tenant` | setup | `stubs/control-plane/create_tenant.py` | `tenant_name`, `tenant_id` |
| `test_access_key` | test | `stubs/control-plane/test_access_key.py` | `authenticated`, `account_id` |
| `disable_access_key` | test | `stubs/control-plane/disable_access_key.py` | `status` |
| `verify_key_rejected` | test | `stubs/control-plane/verify_key_rejected.py` | `rejected`, `error_type` |
| `list_tenants` | test | `stubs/control-plane/list_tenants.py` | `tenants`, `found` |
| `get_tenant` | test | `stubs/control-plane/get_tenant.py` | `tenant_name`, `description` |
| `delete_access_key` | teardown | `stubs/control-plane/delete_access_key.py` | `resources_deleted` |
| `delete_tenant` | teardown | `stubs/control-plane/delete_tenant.py` | `resources_deleted` |

### Image Registry (`image-registry.yaml`)

| Step | Phase | Script | Key JSON Fields |
|------|-------|--------|-----------------|
| `upload_image` | setup | `stubs/image-registry/upload_image.py` | `image_id`, `storage_bucket`, `disk_ids` |
| `crud_image` | test | `stubs/image-registry/crud_image.py` | `image_id`, `operations` |
| `launch_instance` | test | `stubs/image-registry/launch_instance.py` | `instance_id`, `public_ip`, `key_path` |
| `crud_install_config` | test | `stubs/image-registry/crud_install_config.py` | `config_id`, `config_name`, `operations` |
| `install_image_bm` | test | `stubs/image-registry/install_image_bm.py` | `instance_id`, `image_id`, `instance_state` |
| `install_config_bm` | test | `stubs/image-registry/install_config_bm.py` | `instance_id`, `config_id`, `instance_state` |
| `teardown` | teardown | `stubs/image-registry/teardown.py` | `resources_deleted`, `message` |

## Related Documentation

- [External Validation Guide](../../../docs/guides/external-validation-guide.md) — Writing scripts, config format, running validations
- [Configuration Guide](../../../docs/guides/configuration.md) — Full config reference (steps, schemas, templates)
- [AWS Reference Implementation](../../../docs/references/aws.md) — Working AWS examples for all test suites
