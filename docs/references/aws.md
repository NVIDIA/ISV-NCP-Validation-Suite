# AWS Reference Implementation

The AWS implementation is a complete, working example of the ISV validation framework. Use it as a reference when implementing the [provider-agnostic templates](../../isvctl/configs/templates/README.md) for your own platform.

## How Templates and AWS Relate

```text
Template (provider-agnostic)          AWS Reference (working example)
─────────────────────────────         ─────────────────────────────────
templates/vm.yaml                     aws/vm.yaml
templates/stubs/vm/launch_instance.py stubs/aws/vm/launch_instance.py
           ↑ skeleton + TODO                    ↑ full boto3 implementation
```

Each template has a corresponding AWS config and scripts that show exactly how to fill in the TODO blocks.

## Available Modules

| Domain | Config | Scripts | Docs | Template |
|--------|--------|---------|------|----------|
| **IAM** | [`aws/iam.yaml`](../../isvctl/configs/aws/iam.yaml) | [`stubs/aws/iam/`](../../isvctl/configs/stubs/aws/iam/) | [Guide](../../isvctl/configs/stubs/aws/iam/docs/aws-iam.md) | [`templates/iam.yaml`](../../isvctl/configs/templates/iam.yaml) |
| **Network** | [`aws/network.yaml`](../../isvctl/configs/aws/network.yaml) | [`stubs/aws/network/`](../../isvctl/configs/stubs/aws/network/) | [Guide](../../isvctl/configs/stubs/aws/network/docs/aws-network.md) | [`templates/network.yaml`](../../isvctl/configs/templates/network.yaml) |
| **VM** | [`aws/vm.yaml`](../../isvctl/configs/aws/vm.yaml) | [`stubs/aws/vm/`](../../isvctl/configs/stubs/aws/vm/) | [Guide](../../isvctl/configs/stubs/aws/vm/docs/aws-vm.md) | [`templates/vm.yaml`](../../isvctl/configs/templates/vm.yaml) |
| **Bare Metal** | [`aws/bm.yaml`](../../isvctl/configs/aws/bm.yaml) | [`stubs/aws/bm/`](../../isvctl/configs/stubs/aws/bm/) | [Guide](../../isvctl/configs/stubs/aws/bm/docs/aws-bm.md) | [`templates/bm.yaml`](../../isvctl/configs/templates/bm.yaml) |
| **EKS** | [`aws/eks.yaml`](../../isvctl/configs/aws/eks.yaml) | [`stubs/aws/eks/`](../../isvctl/configs/stubs/aws/eks/) | [Guide](../../isvctl/configs/stubs/aws/eks/docs/aws-eks.md) | [`templates/eks.yaml`](../../isvctl/configs/templates/eks.yaml) |
| **Control Plane** | [`aws/control-plane.yaml`](../../isvctl/configs/aws/control-plane.yaml) | [`stubs/aws/control-plane/`](../../isvctl/configs/stubs/aws/control-plane/) | [Guide](../../isvctl/configs/stubs/aws/control-plane/docs/aws-control-plane.md) | [`templates/control-plane.yaml`](../../isvctl/configs/templates/control-plane.yaml) |
| **ISO/Image** | [`aws/iso.yaml`](../../isvctl/configs/aws/iso.yaml) | [`stubs/aws/iso/`](../../isvctl/configs/stubs/aws/iso/) | [Guide](../../isvctl/configs/stubs/aws/iso/docs/aws-iso.md) | [`templates/iso.yaml`](../../isvctl/configs/templates/iso.yaml) |

Shared AWS utilities (error handling, EC2/VPC helpers) are in [`stubs/aws/common/`](../../isvctl/configs/stubs/aws/common/).

## Running AWS Validations

```bash
# Prerequisites: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION set

uv run isvctl test run -f isvctl/configs/aws/iam.yaml
uv run isvctl test run -f isvctl/configs/aws/network.yaml
uv run isvctl test run -f isvctl/configs/aws/vm.yaml
uv run isvctl test run -f isvctl/configs/aws/bm.yaml
uv run isvctl test run -f isvctl/configs/aws/eks.yaml
uv run isvctl test run -f isvctl/configs/aws/control-plane.yaml
uv run isvctl test run -f isvctl/configs/aws/iso.yaml
```

## Using AWS as a Reference

When implementing a template for your platform:

1. Open the template stub (e.g., `templates/stubs/vm/launch_instance.py`)
2. Open the AWS equivalent side-by-side (e.g., `stubs/aws/vm/launch_instance.py`)
3. Replace the TODO block with your platform's API calls, keeping the same JSON output fields
4. Read the AWS domain guide (linked above) for context on what each test validates and why
