# Validation Test Suites

Provider-agnostic test suites -- the **contract** layer of the framework.
Each YAML defines *what* to validate; [provider configs](../providers/) import
them and supply *how* (platform-specific scripts).

- **Adding your own platform?** Start at the [my-isv scaffold](../stubs/my-isv/README.md).
- **New to the framework?** See the [External Validation Guide](../../../docs/guides/external-validation-guide.md).
- **Try it without cloud credentials:** `make demo-test`.

## Available Test Suites

| Test Suite | Domain | Stubs | AWS Reference |
|------------|--------|-------|---------------|
| [`iam.yaml`](iam.yaml) | User lifecycle (create -> verify -> delete) | [`stubs/my-isv/iam/`](../stubs/my-isv/iam/) (3 scripts) | [`providers/aws/iam.yaml`](../providers/aws/iam.yaml) |
| [`network.yaml`](network.yaml) | VPC CRUD, subnets, isolation, SG CRUD, security, connectivity, traffic, DDI, SDN | [`stubs/my-isv/network/`](../stubs/my-isv/network/) (16 scripts) | [`providers/aws/network.yaml`](../providers/aws/network.yaml) |
| [`vm.yaml`](vm.yaml) | GPU VM lifecycle: launch -> tags -> stop/start -> reboot -> describe -> NIM -> teardown | [`stubs/my-isv/vm/`](../stubs/my-isv/vm/) (9 scripts) | [`providers/aws/vm.yaml`](../providers/aws/vm.yaml) |
| [`bare_metal.yaml`](bare_metal.yaml) | BMaaS lifecycle: launch -> tags -> topology -> serial -> stop/start -> reboot -> power-cycle -> NIM -> teardown | [`stubs/my-isv/bare_metal/`](../stubs/my-isv/bare_metal/) (12 scripts) | [`providers/aws/bare_metal.yaml`](../providers/aws/bare_metal.yaml) |
| [`k8s.yaml`](k8s.yaml) | Kubernetes GPU cluster: nodes, GPU operator, scheduling, workloads | [`stubs/my-isv/k8s/`](../stubs/my-isv/k8s/) (9 shell: generic + k3s/microk8s/minikube variants) | [`providers/aws/eks.yaml`](../providers/aws/eks.yaml) |
| [`slurm.yaml`](slurm.yaml) | Slurm HPC cluster: partitions, jobs, GPU allocation | [`stubs/my-isv/slurm/`](../stubs/my-isv/slurm/) (2 shell) | -- |
| [`control-plane.yaml`](control-plane.yaml) | API health, access key lifecycle, tenant lifecycle | [`stubs/my-isv/control-plane/`](../stubs/my-isv/control-plane/) (10 scripts) | [`providers/aws/control-plane.yaml`](../providers/aws/control-plane.yaml) |
| [`image-registry.yaml`](image-registry.yaml) | Image upload, CRUD, VM launch, install config, BMaaS provisioning | [`stubs/my-isv/image-registry/`](../stubs/my-isv/image-registry/) (7 scripts) | [`providers/aws/image-registry.yaml`](../providers/aws/image-registry.yaml) |

## Test Suite Details

### IAM (`iam.yaml`)

| Step | Phase | Script | Key JSON Fields |
|------|-------|--------|-----------------|
| `create_user` | setup | `stubs/my-isv/iam/create_user.py` | `username`, `user_id`, `access_key_id`, `secret_access_key` |
| `test_credentials` | test | `stubs/my-isv/iam/test_credentials.py` | `account_id`, `tests.identity.passed`, `tests.access.passed` |
| `teardown` | teardown | `stubs/my-isv/iam/delete_user.py` | `resources_deleted`, `message` |

### Network (`network.yaml`)

| Step | Phase | Script | What It Tests |
|------|-------|--------|---------------|
| `create_network` | setup | `stubs/my-isv/network/create_vpc.py` | Shared VPC creation |
| `vpc_crud` | test | `stubs/my-isv/network/vpc_crud_test.py` | Create/Read/Update/Delete lifecycle |
| `subnet_config` | test | `stubs/my-isv/network/subnet_test.py` | Multi-AZ subnet distribution |
| `vpc_isolation` | test | `stubs/my-isv/network/isolation_test.py` | Security boundaries between VPCs |
| `sg_crud` | test | `stubs/my-isv/network/sg_crud_test.py` | Security group create/read/update/delete lifecycle |
| `security_blocking` | test | `stubs/my-isv/network/security_test.py` | Firewall/ACL blocking rules |
| `connectivity_test` | test | `stubs/my-isv/network/test_connectivity.py` | Instance network assignment |
| `traffic_validation` | test | `stubs/my-isv/network/traffic_test.py` | Ping allowed/blocked, internet |
| `vpc_ip_config` | test | `stubs/my-isv/network/vpc_ip_config_test.py` | DHCP options, subnet CIDRs, auto-assign IP |
| `dhcp_ip_test` | test | `stubs/my-isv/network/dhcp_ip_test.py` | DHCP lease, IP match, DNS options via SSH |
| `byoip_test` | test | `stubs/my-isv/network/byoip_test.py` | Bring-Your-Own-IP with custom CIDRs |
| `stable_ip_test` | test | `stubs/my-isv/network/stable_ip_test.py` | IP persistence across stop/start |
| `floating_ip_test` | test | `stubs/my-isv/network/floating_ip_test.py` | Atomic IP switch between instances |
| `dns_test` | test | `stubs/my-isv/network/dns_test.py` | Custom internal domain resolution |
| `peering_test` | test | `stubs/my-isv/network/peering_test.py` | Cross-VPC connectivity |
| `teardown` | teardown | `stubs/my-isv/network/teardown.py` | VPC cleanup |

### VM (`vm.yaml`)

| Step | Phase | Script | Key JSON Fields |
|------|-------|--------|-----------------|
| `launch_instance` | setup | `stubs/my-isv/vm/launch_instance.py` | `instance_id`, `public_ip`, `key_file`, `vpc_id` |
| `list_instances` | test | `stubs/my-isv/vm/list_instances.py` | `instances`, `total_count` |
| `verify_tags` | test | `stubs/my-isv/vm/describe_tags.py` | `instance_id`, `tags`, `tag_count` |
| `serial_console` | test | `stubs/my-isv/vm/serial_console.py` | `console_available`, `serial_access_enabled` |
| `stop_instance` | test | `stubs/my-isv/vm/stop_instance.py` | `instance_id`, `state`, `stop_initiated` |
| `start_instance` | test | `stubs/my-isv/vm/start_instance.py` | `instance_id`, `state`, `public_ip`, `ssh_ready` |
| `reboot_instance` | test | `stubs/my-isv/vm/reboot_instance.py` | `reboot_initiated`, `ssh_ready`, `uptime_seconds` |
| `describe_instance` | test | `stubs/my-isv/vm/describe_instance.py` | `instance_id`, `state`, `public_ip`, `key_file` |
| `deploy_nim` | test | `stubs/common/deploy_nim.py` | `container_id`, `health_endpoint` |
| `teardown_nim` | teardown | `stubs/common/teardown_nim.py` | `message` |
| `teardown` | teardown | `stubs/my-isv/vm/teardown.py` | `resources_deleted`, `message` |

### Bare Metal (`bare_metal.yaml`)

| Step | Phase | Script | Key JSON Fields |
|------|-------|--------|-----------------|
| `launch_instance` | setup | `stubs/my-isv/bare_metal/launch_instance.py` | `instance_id`, `public_ip`, `key_file`, `vpc_id` |
| `list_instances` | test | `stubs/my-isv/vm/list_instances.py` | Reuses VM script |
| `verify_tags` | test | `stubs/my-isv/bare_metal/describe_tags.py` | `instance_id`, `tags`, `tag_count` |
| `topology_placement` | test | `stubs/my-isv/bare_metal/topology_placement.py` | `placement_supported`, `operations` |
| `serial_console` | test | `stubs/my-isv/bare_metal/serial_console.py` | `console_available`, `serial_access_enabled` |
| `stop_instance` | test | `stubs/my-isv/bare_metal/stop_instance.py` | `instance_id`, `state`, `stop_initiated` |
| `start_instance` | test | `stubs/my-isv/bare_metal/start_instance.py` | `instance_id`, `state`, `public_ip`, `ssh_ready` |
| `reboot_instance` | test | `stubs/my-isv/bare_metal/reboot_instance.py` | `reboot_initiated`, `ssh_ready`, `uptime_seconds` |
| `power_cycle_instance` | test | `stubs/my-isv/bare_metal/power_cycle_instance.py` | `instance_id`, `state`, `public_ip`, `ssh_ready` |
| `describe_instance` | test | `stubs/my-isv/bare_metal/describe_instance.py` | `instance_state`, `public_ip`, `key_file` |
| `reinstall_instance` | test | `stubs/my-isv/bare_metal/reinstall_instance.py` | `instance_state` (skipped by default) |
| `deploy_nim` | test | `stubs/common/deploy_nim.py` | Shared NIM deployment |
| `teardown_nim` | teardown | `stubs/common/teardown_nim.py` | Shared NIM cleanup |
| `teardown` | teardown | `stubs/my-isv/bare_metal/teardown.py` | `resources_deleted`, `message` |
| `verify_teardown` | teardown | `stubs/my-isv/bare_metal/verify_terminated.py` | `checks.instance_terminated`, `checks.sg_deleted` |

### Kubernetes (`k8s.yaml`)

| Step | Phase | Script |
|------|-------|--------|
| `setup` | setup | `stubs/my-isv/k8s/setup.sh` |
| `teardown` | teardown | `stubs/my-isv/k8s/teardown.sh` |

Validations use `kubectl` directly (or a custom CLI via the `KUBECTL` env var): node counts, GPU operator, pod health, NCCL/NIM workloads.

### Slurm (`slurm.yaml`)

| Step | Phase | Script |
|------|-------|--------|
| `setup` | setup | `stubs/my-isv/slurm/setup.sh` |
| `teardown` | teardown | `stubs/my-isv/slurm/teardown.sh` |

Validations use `sinfo`/`srun` directly: partitions, GPU allocation, job scheduling.

### Control Plane (`control-plane.yaml`)

| Step | Phase | Script | Key JSON Fields |
|------|-------|--------|-----------------|
| `check_api` | setup | `stubs/my-isv/control-plane/check_api.py` | `account_id`, `tests` |
| `create_access_key` | setup | `stubs/my-isv/control-plane/create_access_key.py` | `username`, `access_key_id` |
| `create_tenant` | setup | `stubs/my-isv/control-plane/create_tenant.py` | `tenant_name`, `tenant_id` |
| `test_access_key` | test | `stubs/my-isv/control-plane/test_access_key.py` | `authenticated`, `account_id` |
| `disable_access_key` | test | `stubs/my-isv/control-plane/disable_access_key.py` | `status` |
| `verify_key_rejected` | test | `stubs/my-isv/control-plane/verify_key_rejected.py` | `rejected`, `error_type` |
| `list_tenants` | test | `stubs/my-isv/control-plane/list_tenants.py` | `tenants`, `found` |
| `get_tenant` | test | `stubs/my-isv/control-plane/get_tenant.py` | `tenant_name`, `description` |
| `delete_access_key` | teardown | `stubs/my-isv/control-plane/delete_access_key.py` | `resources_deleted` |
| `delete_tenant` | teardown | `stubs/my-isv/control-plane/delete_tenant.py` | `resources_deleted` |

### Image Registry (`image-registry.yaml`)

| Step | Phase | Script | Key JSON Fields |
|------|-------|--------|-----------------|
| `upload_image` | setup | `stubs/my-isv/image-registry/upload_image.py` | `image_id`, `storage_bucket`, `disk_ids` |
| `crud_image` | test | `stubs/my-isv/image-registry/crud_image.py` | `image_id`, `operations` |
| `launch_instance` | test | `stubs/my-isv/image-registry/launch_instance.py` | `instance_id`, `public_ip`, `key_path` |
| `crud_install_config` | test | `stubs/my-isv/image-registry/crud_install_config.py` | `config_id`, `config_name`, `operations` |
| `install_image_bm` | test | `stubs/my-isv/image-registry/install_image_bm.py` | `instance_id`, `image_id`, `instance_state` |
| `install_config_bm` | test | `stubs/my-isv/image-registry/install_config_bm.py` | `instance_id`, `config_id`, `instance_state` |
| `teardown` | teardown | `stubs/my-isv/image-registry/teardown.py` | `resources_deleted`, `message` |

## Related Documentation

- [my-isv Scaffold](../stubs/my-isv/README.md) -- Copy-and-fill-in stubs for your own platform
- [External Validation Guide](../../../docs/guides/external-validation-guide.md) -- Writing scripts, config format, running validations
- [Configuration Guide](../../../docs/guides/configuration.md) -- Full config reference (steps, schemas, templates)
- [AWS Reference Implementation](../../../docs/references/aws.md) -- Working AWS examples for all test suites
