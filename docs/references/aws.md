# AWS Reference Implementation

The AWS implementation is a complete, working example of the ISV validation framework. Use it as a reference when implementing the [provider-agnostic templates](../../isvctl/configs/tests/README.md) for your own platform.

## How Templates and AWS Relate

```text
Template (provider-agnostic)          AWS Reference (working example)
─────────────────────────────         ─────────────────────────────────
tests/vm.yaml                         providers/aws/vm.yaml
tests/stubs/vm/launch_instance.py     stubs/aws/vm/launch_instance.py
           ↑ skeleton + TODO                    ↑ full boto3 implementation
```

Each template has a corresponding AWS config and scripts that show exactly how to fill in the TODO blocks.

## Available Modules

| Domain | Config | Scripts | Docs | Template |
|--------|--------|---------|------|----------|
| **IAM** | [`aws/iam.yaml`](../../isvctl/configs/providers/aws/iam.yaml) | [`stubs/aws/iam/`](../../isvctl/configs/stubs/aws/iam/) | [Guide](../../isvctl/configs/stubs/aws/iam/docs/aws-iam.md) | [`templates/iam.yaml`](../../isvctl/configs/tests/iam.yaml) |
| **Network** | [`aws/network.yaml`](../../isvctl/configs/providers/aws/network.yaml) | [`stubs/aws/network/`](../../isvctl/configs/stubs/aws/network/) | [Guide](../../isvctl/configs/stubs/aws/network/docs/aws-network.md) | [`templates/network.yaml`](../../isvctl/configs/tests/network.yaml) |
| **VM** | [`aws/vm.yaml`](../../isvctl/configs/providers/aws/vm.yaml) | [`stubs/aws/vm/`](../../isvctl/configs/stubs/aws/vm/) | [Guide](../../isvctl/configs/stubs/aws/vm/docs/aws-vm.md) | [`templates/vm.yaml`](../../isvctl/configs/tests/vm.yaml) |
| **Bare Metal** | [`aws/bm.yaml`](../../isvctl/configs/providers/aws/bm.yaml) | [`stubs/aws/bm/`](../../isvctl/configs/stubs/aws/bm/) | [Guide](../../isvctl/configs/stubs/aws/bm/docs/aws-bm.md) | [`templates/bm.yaml`](../../isvctl/configs/tests/bm.yaml) |
| **EKS** | [`aws/eks.yaml`](../../isvctl/configs/providers/aws/eks.yaml) | [`stubs/aws/eks/`](../../isvctl/configs/stubs/aws/eks/) | [Guide](../../isvctl/configs/stubs/aws/eks/docs/aws-eks.md) | [`templates/kaas.yaml`](../../isvctl/configs/tests/kaas.yaml) |
| **Control Plane** | [`aws/control-plane.yaml`](../../isvctl/configs/providers/aws/control-plane.yaml) | [`stubs/aws/control-plane/`](../../isvctl/configs/stubs/aws/control-plane/) | [Guide](../../isvctl/configs/stubs/aws/control-plane/docs/aws-control-plane.md) | [`templates/control-plane.yaml`](../../isvctl/configs/tests/control-plane.yaml) |
| **Image Registry** | [`aws/image-registry.yaml`](../../isvctl/configs/providers/aws/image-registry.yaml) | [`stubs/aws/image-registry/`](../../isvctl/configs/stubs/aws/image-registry/) | [Guide](../../isvctl/configs/stubs/aws/image-registry/docs/aws-image-registry.md) | [`templates/image-registry.yaml`](../../isvctl/configs/tests/image-registry.yaml) |

Shared AWS utilities (error handling, EC2/VPC helpers) are in [`stubs/aws/common/`](../../isvctl/configs/stubs/aws/common/).

## Running AWS Validations

```bash
# Prerequisites: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION set

uv run isvctl test run -f isvctl/configs/providers/aws/iam.yaml
uv run isvctl test run -f isvctl/configs/providers/aws/network.yaml
uv run isvctl test run -f isvctl/configs/providers/aws/vm.yaml
uv run isvctl test run -f isvctl/configs/providers/aws/bm.yaml
uv run isvctl test run -f isvctl/configs/providers/aws/eks.yaml
uv run isvctl test run -f isvctl/configs/providers/aws/control-plane.yaml
uv run isvctl test run -f isvctl/configs/providers/aws/image-registry.yaml
```

## Using AWS as a Reference

When implementing a template for your platform:

1. Open the template stub (e.g., `templates/stubs/vm/launch_instance.py`)
2. Open the AWS equivalent side-by-side (e.g., `stubs/aws/vm/launch_instance.py`)
3. Replace the TODO block with your platform's API calls, keeping the same JSON output fields
4. Read the AWS domain guide (linked above) for context on what each test validates and why
