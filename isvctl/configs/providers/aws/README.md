# AWS Provider Configs

Provider configs that wire the [provider-agnostic test suites](../../tests/README.md) to AWS-specific [stub scripts](../../stubs/aws/). Each YAML imports a test suite and overrides commands with `boto3`/Terraform implementations.

## Configs

| Config | Domain | Guide |
|--------|--------|-------|
| [`iam.yaml`](iam.yaml) | User lifecycle (create → verify → delete) | [AWS IAM Guide](../../stubs/aws/iam/docs/aws-iam.md) |
| [`network.yaml`](network.yaml) | VPC CRUD, subnets, isolation, security, connectivity | [AWS Network Guide](../../stubs/aws/network/docs/aws-network.md) |
| [`vm.yaml`](vm.yaml) | GPU VM lifecycle (launch → stop/start → reboot → NIM) | [AWS VM Guide](../../stubs/aws/vm/docs/aws-vm.md) |
| [`bare_metal.yaml`](bare_metal.yaml) | BMaaS lifecycle (launch → topology → serial → NIM) | [AWS Bare Metal Guide](../../stubs/aws/bare_metal/docs/aws-bm.md) |
| [`eks.yaml`](eks.yaml) | Kubernetes GPU cluster (nodes, GPU operator, workloads) | [AWS EKS Guide](../../stubs/aws/eks/docs/aws-eks.md) |
| [`control-plane.yaml`](control-plane.yaml) | API health, access keys, tenant lifecycle | [AWS Control Plane Guide](../../stubs/aws/control-plane/docs/aws-control-plane.md) |
| [`image-registry.yaml`](image-registry.yaml) | Image upload, CRUD, VM launch, install config | [AWS Image Registry Guide](../../stubs/aws/image-registry/docs/aws-image-registry.md) |

## Quick Start

```bash
# Prerequisites: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION set

uv run isvctl test run -f isvctl/configs/providers/aws/iam.yaml
uv run isvctl test run -f isvctl/configs/providers/aws/network.yaml
uv run isvctl test run -f isvctl/configs/providers/aws/vm.yaml
```

## See Also

- [AWS Reference Implementation](../../../../docs/references/aws.md) — Full overview of templates vs AWS, usage patterns
- [Test Suites](../../tests/README.md) — Provider-agnostic test definitions
- [AWS Stub Scripts](../../stubs/aws/) — The scripts these configs invoke
