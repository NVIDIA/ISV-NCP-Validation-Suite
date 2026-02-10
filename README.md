# NVIDIA ISV Lab Tools

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

Validation and management tools for NVIDIA ISV Lab environments.

## Packages

- **isvctl** - Unified controller for cluster lifecycle orchestration
- **isvtest** - Validation framework for Kubernetes, Slurm, and bare metal
- **isvreporter** - Test results reporter for ISV Lab Service

## Quick Start

```bash
# Clone and install
git clone <repo-url>
cd nv-isv-tools
uv sync

# Run validation tests
uv run isvctl test run -f isvctl/configs/k8s.yaml       # Kubernetes
uv run isvctl test run -f isvctl/configs/microk8s.yaml  # MicroK8s
uv run isvctl test run -f isvctl/configs/slurm.yaml     # Slurm
```

For remote ISV clusters without source access, install from NGC (see
[Environment Variables](#environment-variables) for required credentials):

```bash
export NGC_API_KEY=your_api_key
export NGC_ORG=your_org_id
export NGC_TEAM=your_team
export ISV_TOOLS_VERSION=latest
curl -fsSL -H "Authorization: Bearer ${NGC_API_KEY}" \
  "https://api.ngc.nvidia.com/v2/org/${NGC_ORG}/team/${NGC_TEAM}/resources/ncp-isv-lab-scripts/versions/${ISV_TOOLS_VERSION}/files/install.sh" \
  | bash -s -- "${ISV_TOOLS_VERSION}"
```

## Documentation

See [docs/](docs/) for full documentation:

- [Getting Started](docs/getting-started.md) - Installation and first steps

### Guides

- [Configuration](docs/guides/configuration.md) - Config file format and options
- [External Validation](docs/guides/external-validation-guide.md) - Create custom validations without modifying the repo
- [Remote Deployment](docs/guides/remote-deployment.md) - Deploy and run tests remotely
- [Local Development](docs/guides/local-development.md) - MicroK8s setup for local testing

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
| `NGC_API_KEY` | Required for downloading from NGC (installer only) |
| `NGC_NIM_API_KEY` | Required for NIM model benchmarks |
| `NGC_ORG` | NGC organization ID (for NGC install script) |
| `NGC_TEAM` | NGC team name (for NGC install script) |
| `ISV_CLIENT_ID` | Required for ISV Lab Service uploads |
| `ISV_CLIENT_SECRET` | Required for ISV Lab Service uploads |
| `ISV_LAB_SERVICE_ENDPOINT` | Override ISV Lab Service endpoint URL |
| `ISV_SSA_ISSUER` | Override SSA issuer URL |
| `ISV_ENV` | Environment mode: `staging` or `production` |

## License

See [LICENSE](LICENSE) for license information.
