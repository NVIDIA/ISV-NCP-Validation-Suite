# AWS Stub Scripts

AWS implementations of the [provider-agnostic stub scripts](../). Each domain folder contains Python/Bash scripts that perform cloud operations via `boto3` or Terraform and output structured JSON to stdout.

These scripts are invoked by the [AWS provider configs](../../providers/aws/).

## Domains

| Domain | Scripts | Guide |
|--------|---------|-------|
| [`iam/`](iam/) | User create/delete, credential testing | [AWS IAM Guide](iam/docs/aws-iam.md) |
| [`network/`](network/) | VPC CRUD, subnets, isolation, SG CRUD, security, connectivity | [AWS Network Guide](network/docs/aws-network.md) |
| [`vm/`](vm/) | Instance launch, stop/start, reboot, serial console | [AWS VM Guide](vm/docs/aws-vm.md) |
| [`bare_metal/`](bare_metal/) | BM launch, topology, serial console, reinstall | [AWS Bare Metal Guide](bare_metal/docs/aws-bm.md) |
| [`eks/`](eks/) | EKS cluster setup/teardown (Terraform) | [AWS EKS Guide](eks/docs/aws-eks.md) |
| [`control-plane/`](control-plane/) | API checks, access keys, tenant management | [AWS Control Plane Guide](control-plane/docs/aws-control-plane.md) |
| [`image-registry/`](image-registry/) | Image upload/CRUD, install configs, BM provisioning | [AWS Image Registry Guide](image-registry/docs/aws-image-registry.md) |
| [`common/`](common/) | Shared utilities (error handling, EC2/VPC helpers) | - |

## See Also

- [AWS Reference Implementation](../../../../docs/references/aws.md) - Full overview, how templates map to AWS
- [AWS Provider Configs](../../providers/aws/) - YAML configs that invoke these scripts
- [External Validation Guide](../../../../docs/guides/external-validation-guide.md) - Writing scripts, JSON output format
