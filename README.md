# NVIDIA ISV NCP Validation Suite

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

Validation and management tools for NVIDIA ISV Lab environments.

> [!WARNING]
> **Experimental Preview Release**
> This is an experimental/preview release of ISV-NCP-Validation-Suite. Use at your own risk in production environments. The software is provided "as is" without warranties of any kind. Features, APIs, and configurations may change without notice in future releases. For production deployments, thoroughly test in non-critical environments first.

## Packages

- **isvctl** - Unified controller for cluster lifecycle orchestration
- **isvtest** - Validation framework for Kubernetes, Slurm, and bare metal
- **isvreporter** - Test results reporter for ISV Lab Service

## Adding Your Platform

Start from the **provider-agnostic templates** — copy, implement the stub scripts for your cloud/platform, and run:

```bash
cp -r isvctl/configs/tests/ isvctl/configs/my-isv/
# Edit the stub scripts for your platform
uv run isvctl test run -f isvctl/configs/my-isv/vm.yaml
```

Templates are available for: [IAM](isvctl/configs/tests/iam.yaml) | [Network](isvctl/configs/tests/network.yaml) | [VM](isvctl/configs/tests/vm.yaml) | [Bare Metal](isvctl/configs/tests/bm.yaml) | [Kubernetes](isvctl/configs/tests/kaas.yaml) | [Control Plane](isvctl/configs/tests/control-plane.yaml) | [Image Registry](isvctl/configs/tests/image-registry.yaml)

See the [Templates README](isvctl/configs/tests/README.md) for the full guide, and the [AWS Reference Implementation](docs/references/aws.md) as a working example.

## Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python package manager)

## Quick Start

```bash
# Clone and install
git clone https://github.com/NVIDIA/ISV-NCP-Validation-Suite.git
cd ISV-NCP-Validation-Suite
uv sync

# Run validation tests
uv run isvctl test run -f isvctl/configs/tests/k8s.yaml       # Kubernetes
uv run isvctl test run -f isvctl/configs/providers/microk8s.yaml  # MicroK8s
uv run isvctl test run -f isvctl/configs/tests/slurm.yaml     # Slurm
```

## Documentation

See [docs/](docs/) for full documentation:

- [Getting Started](docs/getting-started.md) - Installation and first steps

### Guides

- [Configuration](docs/guides/configuration.md) - Config file format and options
- [External Validation](docs/guides/external-validation-guide.md) - Create custom validations without modifying the repo
- [Remote Deployment](docs/guides/remote-deployment.md) - Deploy and run tests remotely
- [Local Development](docs/guides/local-development.md) - MicroK8s setup for local testing

### References

- [Validation Templates](isvctl/configs/tests/README.md) - Provider-agnostic templates for adding your platform
- [AWS Reference Implementation](docs/references/aws.md) - Working AWS examples for all validation domains

### Package Reference

- [isvctl](docs/packages/isvctl.md) - Controller documentation
- [isvtest](docs/packages/isvtest.md) - Validation framework
- [isvreporter](docs/packages/isvreporter.md) - Reporter documentation

## Development

```bash
make help      # Show available targets
make test      # Run tests for all packages
make lint      # Run linting
make build     # Build all packages
```

See [Contributing](docs/contributing.md) for development setup and guidelines.

## Environment Variables

| Variable | Description |
| -------- | ----------- |
| `ISV_SERVICE_ENDPOINT` | Required for ISV Lab Service uploads |
| `ISV_SSA_ISSUER` | Required for ISV Lab Service uploads |
| `ISV_CLIENT_ID` | Required for ISV Lab Service uploads |
| `ISV_CLIENT_SECRET` | Required for ISV Lab Service uploads |
| `NGC_API_KEY` | Required for NIM model benchmarks |

## License

See [LICENSE](LICENSE) for license information.
