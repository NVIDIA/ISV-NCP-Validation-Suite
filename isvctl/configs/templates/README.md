# Validation Templates

Provider-agnostic validation templates for ISV Lab tests. Templates define **what to validate** (checks); provider configs define **how to provision** (stubs).

## How It Works

```text
┌──────────────────┐     ┌──────────────────────┐     ┌────────────────────┐
│  Template YAML   │     │  Provider YAML       │     │   Validations      │
│  (validations)   │     │  (commands + stubs)   │     │  (check JSON)      │
│                  │     │                      │     │                    │
│  WHAT to check   │  +  │  HOW to provision    │  =  │  Already provided  │
│  K8sNodeReady,   │     │  YOUR stub scripts   │     │  StepSuccessCheck, │
│  GpuCapacity...  │     │  call your API       │     │  FieldExistsCheck  │
└──────────────────┘     └──────────────────────┘     └────────────────────┘
```

**Two ways to use templates:**

1. **Layered** (recommended for new providers): pair a template with a provider config
   ```bash
   isvctl test run -f templates/kaas.yaml -f my-provider/kaas.yaml
   ```

2. **Self-contained** (existing approach): copy a template and add commands inline
   ```bash
   isvctl test run -f my-provider/kaas.yaml  # has both commands + validations
   ```

**The contract is JSON.** Your scripts can be written in any language (Python, Bash, Go, etc.). They just need to print a JSON object to stdout with the required fields.

## Available Templates

| Template | Validations | Provider Stubs | Reference Implementation |
|----------|-------------|----------------|--------------------------|
| `kaas.yaml` | K8s cluster health, GPU operator, GPU scheduling, workloads | `stubs/kaas/` (2 scripts) | `../aws/eks.yaml` |
| `control-plane.yaml` | API health, access key lifecycle, tenant lifecycle | `stubs/control-plane/` (10 scripts) | `../aws/control-plane.yaml` |
| `iam.yaml` | User create, verify credentials, delete | `stubs/iam/` (3 scripts) | `../aws/iam.yaml` |
| `network.yaml` | VPC CRUD, subnets, isolation, security, connectivity | `stubs/network/` (8 scripts) | `../aws/network.yaml` |
| `vm.yaml` | GPU VM lifecycle, SSH, NIM inference | `stubs/vm/` (4 scripts) + `stubs/common/` (2) | `../aws/vm.yaml` |
| `bm.yaml` | Bare-metal lifecycle, SSH, GPU, NIM | `stubs/bm/` (5 scripts) + `stubs/common/` (2) | `../aws/bm.yaml` |
| `image-registry.yaml` | Image upload, install config CRUD, BMaaS install | `stubs/image-registry/` (6 scripts) | `../aws/image-registry.yaml` |

## Context Variables

Templates use `{{ context.variable | default('value') }}` for provider-specific values.
Providers set these via the `context:` block in their YAML:

```yaml
# my-provider/kaas.yaml
context:
  node_count: "5"
  total_gpus: "20"
  gpu_per_node: "4"
  gpu_operator_ns: "nvidia-gpu-operator"
```

Or override at runtime:
```bash
isvctl test run -f templates/kaas.yaml -f my-provider/kaas.yaml \
  --set context.node_count=10
```

## Quick Start

### Layered approach (new providers)

```bash
# 1. Create a provider config with just commands + context
cat > isvctl/configs/my-isv/kaas.yaml << 'EOF'
version: "1.0"
commands:
  kubernetes:
    phases: ["setup", "test", "teardown"]
    steps:
      - name: provision_cluster
        phase: setup
        command: "../stubs/my-isv/kaas/setup.sh"
        timeout: 1800
      - name: teardown_cluster
        phase: teardown
        command: "../stubs/my-isv/kaas/teardown.sh"
        timeout: 1800
context:
  node_count: "3"
  total_gpus: "12"
EOF

# 2. Implement the stub scripts
vim isvctl/configs/stubs/my-isv/kaas/setup.sh

# 3. Run with the template
isvctl test run -f isvctl/configs/templates/kaas.yaml -f isvctl/configs/my-isv/kaas.yaml
```

### Copy approach (existing workflow)

```bash
# 1. Copy the template folder
cp -r isvctl/configs/templates/ isvctl/configs/my-isv/

# 2. Pick a template (e.g., vm) and edit the stub scripts
#    Each stub has a TODO block showing what to implement
vim isvctl/configs/my-isv/stubs/vm/launch_instance.py

# 3. Run the validation
uv run isvctl test run -f isvctl/configs/my-isv/vm.yaml
```

## Template Details

### IAM (`iam.yaml`)

Tests user account lifecycle: create user → verify credentials → delete user.

| Step | Phase | Script | Key JSON Fields |
|------|-------|--------|-----------------|
| `create_user` | setup | `stubs/iam/create_user.py` | `username`, `user_id`, `access_key_id`, `secret_access_key` |
| `test_credentials` | test | `stubs/iam/test_credentials.py` | `account_id`, `tests.identity.passed`, `tests.access.passed` |
| `teardown` | teardown | `stubs/iam/delete_user.py` | `resources_deleted`, `message` |

### Network (`network.yaml`)

Comprehensive network validation with 6 test suites plus shared VPC setup/teardown.

| Step | Phase | Script | What It Tests |
|------|-------|--------|---------------|
| `create_network` | setup | `stubs/network/create_vpc.py` | Shared VPC creation |
| `vpc_crud` | test | `stubs/network/vpc_crud_test.py` | Create/Read/Update/Delete lifecycle |
| `subnet_config` | test | `stubs/network/subnet_test.py` | Multi-AZ subnet distribution |
| `vpc_isolation` | test | `stubs/network/isolation_test.py` | Security boundaries between VPCs |
| `security_blocking` | test | `stubs/network/security_test.py` | Firewall/ACL blocking rules |
| `connectivity_test` | test | `stubs/network/test_connectivity.py` | Instance network assignment |
| `traffic_validation` | test | `stubs/network/traffic_test.py` | Ping allowed/blocked, internet |
| `teardown` | teardown | `stubs/network/teardown.py` | VPC cleanup |

### VM (`vm.yaml`)

GPU virtual machine lifecycle with SSH, GPU, host OS, and NIM inference validations.

| Step | Phase | Script | Key JSON Fields |
|------|-------|--------|-----------------|
| `launch_instance` | setup | `stubs/vm/launch_instance.py` | `instance_id`, `public_ip`, `key_file`, `vpc_id` |
| `list_instances` | test | `stubs/vm/list_instances.py` | `instances`, `total_count` |
| `reboot_instance` | test | `stubs/vm/reboot_instance.py` | `uptime_seconds`, `ssh_connectivity` |
| `deploy_nim` | test | `stubs/common/deploy_nim.py` | `container_id`, `health_endpoint` |
| `teardown_nim` | teardown | `stubs/common/teardown_nim.py` | `message` |
| `teardown` | teardown | `stubs/vm/teardown.py` | `resources_deleted`, `message` |

### Bare Metal (`bm.yaml`)

Bare-metal GPU instance lifecycle. Similar to VM but with longer timeouts for hardware POST/BIOS and post-teardown verification.

| Step | Phase | Script | Key JSON Fields |
|------|-------|--------|-----------------|
| `launch_instance` | setup | `stubs/bm/launch_instance.py` | `instance_id`, `public_ip`, `key_file`, `vpc_id` |
| `list_instances` | test | `stubs/vm/list_instances.py` | Reuses VM script |
| `describe_instance` | test | `stubs/bm/describe_instance.py` | `instance_state`, `public_ip`, `key_file` |
| `reboot_instance` | test | `stubs/bm/reboot_instance.py` | `uptime_seconds`, `ssh_connectivity` |
| `deploy_nim` | test | `stubs/common/deploy_nim.py` | Shared NIM deployment |
| `teardown_nim` | teardown | `stubs/common/teardown_nim.py` | Shared NIM cleanup |
| `teardown` | teardown | `stubs/bm/teardown.py` | `resources_deleted`, `message` |
| `verify_teardown` | teardown | `stubs/bm/verify_terminated.py` | `checks.instance_terminated`, `checks.sg_deleted` |

### Kubernetes / KaaS (`kaas.yaml`)

GPU-enabled Kubernetes cluster provisioning and validation. Uses shell scripts for cluster lifecycle.

| Step | Phase | Script | Key JSON Fields |
|------|-------|--------|-----------------|
| `provision_cluster` | setup | `stubs/kaas/setup.sh` | `cluster_name`, `cluster_endpoint`, `node_count` |
| `teardown_cluster` | teardown | `stubs/kaas/teardown.sh` | `message` |

Validations use `kubectl` directly: node counts, GPU operator, pod health, NCCL/NIM workloads.

### Control Plane (`control-plane.yaml`)

API health, access key lifecycle, and tenant management.

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

Image registry lifecycle: OS image upload/import, VM launch, install config CRUD, and BMaaS provisioning.

| Step | Phase | Script | Key JSON Fields |
|------|-------|--------|-----------------|
| `upload_image` | setup | `stubs/image-registry/upload_image.py` | `image_id`, `storage_bucket`, `disk_ids` |
| `launch_instance` | test | `stubs/image-registry/launch_instance.py` | `instance_id`, `public_ip`, `key_path` |
| `crud_install_config` | test | `stubs/image-registry/crud_install_config.py` | `config_id`, `config_name`, `operations` |
| `install_image_bm` | test | `stubs/image-registry/install_image_bm.py` | `instance_id`, `image_id`, `instance_state` |
| `install_config_bm` | test | `stubs/image-registry/install_config_bm.py` | `instance_id`, `config_id`, `instance_state` |
| `teardown` | teardown | `stubs/image-registry/teardown.py` | `resources_deleted`, `message` |

## JSON Output Contract

Each script must print **one JSON object** to stdout. The minimum required fields vary by step (see each template's YAML comments and stub docstrings for details).

### Success Pattern

```json
{
  "success": true,
  "platform": "<domain>",
  "field1": "value1",
  "field2": "value2"
}
```

### Failure Pattern

```json
{
  "success": false,
  "platform": "<domain>",
  "error": "descriptive error message"
}
```

> Scripts should also use process exit codes (`0` for success, non-zero for failure) so failures are visible in step execution logs.

## Validations Reference

The templates use these built-in validations (you don't need to modify these):

| Validation | What it checks |
|-----------|----------------|
| `StepSuccessCheck` | `success == true` in JSON output |
| `FieldExistsCheck` | Named fields exist and are non-empty |
| `FieldValueCheck` | Field matches expected value |
| `InstanceStateCheck` | Instance state matches expected (e.g., "running") |
| `InstanceListCheck` | Instance list has minimum count |
| `InstanceRebootCheck` | Reboot succeeded (uptime, SSH, state) |
| `NetworkProvisionedCheck` | Network created with required subnets |
| `VpcCrudCheck` | VPC CRUD operations all passed |
| `SubnetConfigCheck` | Subnets configured correctly |
| `VpcIsolationCheck` | VPCs are properly isolated |
| `SecurityBlockingCheck` | Firewall rules block correctly |
| `NetworkConnectivityCheck` | Network connectivity verified |
| `TrafficFlowCheck` | Traffic flows as expected |
| `SshConnectivityCheck` | SSH connection succeeds |
| `SshGpuCheck` | GPU detected via nvidia-smi |
| `SshHostSoftwareCheck` | Host OS / driver stack verified |
| `SshNimHealthCheck` | NIM health endpoint responds |
| `SshNimInferenceCheck` | NIM inference returns result |
| `AccessKeyCreatedCheck` | Access key fields present |
| `AccessKeyAuthenticatedCheck` | Key authenticates successfully |
| `AccessKeyDisabledCheck` | Key disabled confirmation |
| `AccessKeyRejectedCheck` | Disabled key is rejected |
| `TenantCreatedCheck` | Tenant fields present |
| `TenantListedCheck` | Tenant appears in list |
| `TenantInfoCheck` | Tenant details retrievable |

## Tips

- **Any language works** - scripts can be Python, Bash, Go, curl-based, etc.
- **Jinja2 templating** - use `{{steps.create_user.username}}` to pass data between steps
- **Sensitive args** - use `sensitive_args` in the YAML to mask secrets in logs
- **Skip teardown** - set env vars like `BM_SKIP_TEARDOWN=true` to keep resources for debugging
- **Extra fields are fine** - JSON output can include additional fields beyond the required ones
- **Shared scripts** - `stubs/common/` contains scripts reused across templates (e.g., NIM deployment)
- **Dev workflow** - BM and VM templates support reusing existing instances via environment variables
