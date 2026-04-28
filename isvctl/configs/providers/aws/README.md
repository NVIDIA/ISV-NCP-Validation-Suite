# AWS Provider Configs

Provider configs that wire the [provider-agnostic test suites](../../suites/README.md) to AWS-specific [scripts](scripts/). Each YAML imports a suite and overrides commands with `boto3`/Terraform implementations.

## Configs

| Config | Domain | Guide |
|--------|--------|-------|
| [`config/iam.yaml`](config/iam.yaml) | User lifecycle (create -> verify -> delete) | [AWS IAM Guide](scripts/iam/docs/aws-iam.md) |
| [`config/network.yaml`](config/network.yaml) | VPC CRUD, subnets, isolation, SG CRUD, security, connectivity | [AWS Network Guide](scripts/network/docs/aws-network.md) |
| [`config/vm.yaml`](config/vm.yaml) | GPU VM lifecycle (launch -> stop/start -> reboot -> NIM) | [AWS VM Guide](scripts/vm/docs/aws-vm.md) |
| [`config/bare_metal.yaml`](config/bare_metal.yaml) | BMaaS lifecycle (launch -> topology -> serial -> NIM) | [AWS Bare Metal Guide](scripts/bare_metal/docs/aws-bm.md) |
| [`config/eks.yaml`](config/eks.yaml) | Kubernetes GPU cluster (nodes, GPU operator, workloads) | [AWS EKS Guide](scripts/eks/docs/aws-eks.md) |
| [`config/control-plane.yaml`](config/control-plane.yaml) | API health, access keys, tenant lifecycle | [AWS Control Plane Guide](scripts/control-plane/docs/aws-control-plane.md) |
| [`config/image-registry.yaml`](config/image-registry.yaml) | Image upload, CRUD, VM launch, install config | [AWS Image Registry Guide](scripts/image-registry/docs/aws-image-registry.md) |
| [`config/security.yaml`](config/security.yaml) | BMC isolation, BMC protocol security, API endpoint isolation, SA credential auth | - |

## Quick Start

```bash
# Prerequisites: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION set

uv run isvctl test run -f isvctl/configs/providers/aws/config/iam.yaml
uv run isvctl test run -f isvctl/configs/providers/aws/config/network.yaml
uv run isvctl test run -f isvctl/configs/providers/aws/config/vm.yaml
```

## See Also

- [AWS Reference Implementation](../../../../docs/references/aws.md) - Full overview of suites vs AWS, usage patterns
- [Validation Suites](../../suites/README.md) - Provider-agnostic test definitions
- [AWS Scripts](scripts/) - The scripts these configs invoke
