# Carbide Provider

Provider implementation for [NVIDIA Carbide](https://github.com/fabiendupont/cloud-provider-nvidia-carbide) bare-metal infrastructure management. Uses `carbidecli` to interact with the Carbide API.

## Template Coverage

| Template | Carbide Config | Status |
|----------|---------------|--------|
| `control-plane` | `control-plane.yaml` | SSH key + VPC lifecycle |
| `network` | `network.yaml` | VPC, subnet, prefix, NSG |
| `image-registry` | `image-registry.yaml` | OperatingSystem + InstanceType CRUD |
| `bm` | `bm.yaml` | Instance launch/describe/reboot/teardown |
| `iam` | `iam.yaml` | Token validation, scope coverage, write access |
| `vm` | — | Not applicable (VMs are a platform concern, e.g., KubeVirt) |
| `kaas` | — | Not applicable (K8s installation is a platform concern) |

## Usage

```bash
# IAM: token validation + scope coverage (run first)
isvctl test run \
  -f isvctl/configs/templates/iam.yaml \
  -f isvctl/configs/carbide/iam.yaml

# Control plane validation
isvctl test run \
  -f isvctl/configs/templates/control-plane.yaml \
  -f isvctl/configs/carbide/control-plane.yaml

# Network validation
CARBIDE_SITE_ID=<uuid> isvctl test run \
  -f isvctl/configs/templates/network.yaml \
  -f isvctl/configs/carbide/network.yaml

# Image registry validation
CARBIDE_SITE_ID=<uuid> isvctl test run \
  -f isvctl/configs/templates/image-registry.yaml \
  -f isvctl/configs/carbide/image-registry.yaml

# Bare metal instance validation
CARBIDE_SITE_ID=<uuid> CARBIDE_OS_ID=<uuid> CARBIDE_INSTANCE_TYPE=<uuid> \
  isvctl test run \
    -f isvctl/configs/templates/bm.yaml \
    -f isvctl/configs/carbide/bm.yaml
```

## Authentication

`carbidecli` handles authentication via its own config (`~/.carbide/config.yaml`) or environment variables:

| Variable | Description |
|----------|-------------|
| `CARBIDE_TOKEN` | API bearer token |
| `CARBIDE_API_KEY` | NGC API key |
| `CARBIDE_ORG` | Organization/tenant name |

## Required Environment Variables

| Variable | Used by | Description |
|----------|---------|-------------|
| `CARBIDE_SITE_ID` | network, image-registry, bm | Site UUID for resource creation |
| `CARBIDE_OS_ID` | bm | Operating system UUID for instance provisioning |
| `CARBIDE_INSTANCE_TYPE` | bm | Instance type UUID (hardware profile) |
| `CARBIDE_VPC_ID` | bm (optional) | Pre-existing VPC to use |
| `CARBIDE_SSH_KEY_GROUP` | bm (optional) | SSH key group for instance access |

## Extending for Platforms

Carbide provides bare-metal infrastructure. Platforms (OpenShift, RHEL+Slurm, etc.) build on top:

```bash
# OpenShift on Carbide
isvctl test run \
  -f isvctl/configs/templates/kaas.yaml \
  -f isvctl/configs/openshift/kaas-provision.yaml    # AI + Carbide orchestration
  -f isvctl/configs/openshift/kaas-overrides.yaml     # OpenShift-specific checks

# RHEL + Slurm on Carbide
isvctl test run \
  -f isvctl/configs/templates/bm.yaml \
  -f isvctl/configs/carbide/bm.yaml \
  -f isvctl/configs/slurm/bm-overrides.yaml           # Slurm-specific checks
```

The platform layer handles:
- Orchestrating K8s/Slurm installation on Carbide bare metal
- Platform-specific operators (GPU Operator, Network Operator)
- Platform-specific validations (KubeVirt, DRA, ComputeDomains)
