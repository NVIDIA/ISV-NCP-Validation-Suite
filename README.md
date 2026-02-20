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
cp -r isvctl/configs/templates/ isvctl/configs/my-isv/
# Edit the stub scripts for your platform
uv run isvctl test run -f isvctl/configs/my-isv/vm.yaml
```

Templates are available for: [IAM](isvctl/configs/templates/iam.yaml) | [Network](isvctl/configs/templates/network.yaml) | [VM](isvctl/configs/templates/vm.yaml) | [Bare Metal](isvctl/configs/templates/bm.yaml) | [Kubernetes](isvctl/configs/templates/eks.yaml) | [Control Plane](isvctl/configs/templates/control-plane.yaml) | [ISO/Image Import](isvctl/configs/templates/iso.yaml)

See the [Templates README](isvctl/configs/templates/README.md) for the full guide, and the [AWS Reference Implementation](docs/references/aws.md) as a working example.

## Quick Start

```bash
# Clone and install
git clone https://github.com/NVIDIA/ISV-NCP-Validation-Suite.git
cd ISV-NCP-Validation-Suite
uv sync

# Run validation tests
uv run isvctl test run -f isvctl/configs/k8s.yaml       # Kubernetes
uv run isvctl test run -f isvctl/configs/microk8s.yaml  # MicroK8s
uv run isvctl test run -f isvctl/configs/slurm.yaml     # Slurm
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

- [Validation Templates](isvctl/configs/templates/README.md) - Provider-agnostic templates for adding your platform
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
| `NGC_NIM_API_KEY` | Required for NIM model benchmarks |
| `ISV_SERVICE_ENDPOINT` | Required for ISV Lab Service uploads |
| `ISV_SSA_ISSUER` | Required for ISV Lab Service uploads |
| `ISV_CLIENT_ID` | Required for ISV Lab Service uploads |
| `ISV_CLIENT_SECRET` | Required for ISV Lab Service uploads |

## License

See [LICENSE](LICENSE) for license information.
