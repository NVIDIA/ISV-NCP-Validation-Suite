# AWS Reference Implementation

The AWS implementation is a complete, working example of the ISV validation framework. Use it as a reference when implementing the [provider-agnostic templates](../../isvctl/configs/tests/README.md) for your own platform.

## How Templates and AWS Relate

```text
Template (provider-agnostic)             AWS Reference (working example)
─────────────────────────────            ─────────────────────────────────
tests/vm.yaml                            providers/aws/vm.yaml
stubs/my-isv/vm/launch_instance.py       stubs/aws/vm/launch_instance.py
     ↑ TODO block + demo-mode fallback         ↑ full boto3 implementation
```

Each template has a corresponding AWS config and scripts that show exactly how to fill in the TODO blocks.

## Available Modules

| Domain | Config | Scripts | Docs | Test Suite |
|--------|--------|---------|------|------------|
| **IAM** | [`providers/aws/iam.yaml`](../../isvctl/configs/providers/aws/iam.yaml) | [`stubs/aws/iam/`](../../isvctl/configs/stubs/aws/iam/) | [Guide](../../isvctl/configs/stubs/aws/iam/docs/aws-iam.md) | [`tests/iam.yaml`](../../isvctl/configs/tests/iam.yaml) |
| **Network** | [`providers/aws/network.yaml`](../../isvctl/configs/providers/aws/network.yaml) | [`stubs/aws/network/`](../../isvctl/configs/stubs/aws/network/) | [Guide](../../isvctl/configs/stubs/aws/network/docs/aws-network.md) | [`tests/network.yaml`](../../isvctl/configs/tests/network.yaml) |
| **VM** | [`providers/aws/vm.yaml`](../../isvctl/configs/providers/aws/vm.yaml) | [`stubs/aws/vm/`](../../isvctl/configs/stubs/aws/vm/) | [Guide](../../isvctl/configs/stubs/aws/vm/docs/aws-vm.md) | [`tests/vm.yaml`](../../isvctl/configs/tests/vm.yaml) |
| **Bare Metal** | [`providers/aws/bare_metal.yaml`](../../isvctl/configs/providers/aws/bare_metal.yaml) | [`stubs/aws/bare_metal/`](../../isvctl/configs/stubs/aws/bare_metal/) | [Guide](../../isvctl/configs/stubs/aws/bare_metal/docs/aws-bm.md) | [`tests/bare_metal.yaml`](../../isvctl/configs/tests/bare_metal.yaml) |
| **EKS** | [`providers/aws/eks.yaml`](../../isvctl/configs/providers/aws/eks.yaml) | [`stubs/aws/eks/`](../../isvctl/configs/stubs/aws/eks/) | [Guide](../../isvctl/configs/stubs/aws/eks/docs/aws-eks.md) | [`tests/k8s.yaml`](../../isvctl/configs/tests/k8s.yaml) |
| **Control Plane** | [`providers/aws/control-plane.yaml`](../../isvctl/configs/providers/aws/control-plane.yaml) | [`stubs/aws/control-plane/`](../../isvctl/configs/stubs/aws/control-plane/) | [Guide](../../isvctl/configs/stubs/aws/control-plane/docs/aws-control-plane.md) | [`tests/control-plane.yaml`](../../isvctl/configs/tests/control-plane.yaml) |
| **Image Registry** | [`providers/aws/image-registry.yaml`](../../isvctl/configs/providers/aws/image-registry.yaml) | [`stubs/aws/image-registry/`](../../isvctl/configs/stubs/aws/image-registry/) | [Guide](../../isvctl/configs/stubs/aws/image-registry/docs/aws-image-registry.md) | [`tests/image-registry.yaml`](../../isvctl/configs/tests/image-registry.yaml) |

Shared AWS utilities (error handling, EC2/VPC helpers) are in [`stubs/aws/common/`](../../isvctl/configs/stubs/aws/common/).

## Running AWS Validations

```bash
# Prerequisites: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION set

uv run isvctl test run -f isvctl/configs/providers/aws/iam.yaml
uv run isvctl test run -f isvctl/configs/providers/aws/network.yaml
uv run isvctl test run -f isvctl/configs/providers/aws/vm.yaml
uv run isvctl test run -f isvctl/configs/providers/aws/bare_metal.yaml
uv run isvctl test run -f isvctl/configs/providers/aws/eks.yaml
uv run isvctl test run -f isvctl/configs/providers/aws/control-plane.yaml
uv run isvctl test run -f isvctl/configs/providers/aws/image-registry.yaml
```

## Using AWS as a Reference

When implementing a template for your platform:

1. Open the template stub (e.g., `stubs/my-isv/vm/launch_instance.py`)
2. Open the AWS equivalent side-by-side (e.g., `stubs/aws/vm/launch_instance.py`)
3. Replace the TODO block with your platform's API calls, keeping the same JSON output fields
4. Read the AWS domain guide (linked above) for context on what each test validates and why
5. Run `make smoke-test` at any point to smoke-test your progress without real credentials
