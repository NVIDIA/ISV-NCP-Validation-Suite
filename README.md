# NVIDIA ISV NCP Validation Suite

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

Validation and management tools for NVIDIA ISV Lab environments.

> [!WARNING]
> **Experimental Preview Release**
> This is an experimental/preview release of ISV-NCP-Validation-Suite. Use at your own risk in production environments. The software is provided "as is" without warranties of any kind. Features, APIs, and configurations may change without notice in future releases. For production deployments, thoroughly test in non-critical environments first.

## What Is This?

The ISV NCP Validation Suite is a test framework for validating that developers and compute providers get the most from their NVIDIA hardware across a range of common compute offerings.

It consists of a very flexible set of tests, which ensure that a system is able to support AI training, inferencing, and running AI-enabled applications, along with more traditional cloud services.

This validation suite is meant to be run against an existing cloud system, specifically one that is running NVIDIA hardware. This suite is not itself a cloud software platform, nor does it target a single specific cloud platform. Instead, it maps high-level requirements to a set of *stub* functions, which allow you to run high-level operations (like "Create a Virtual Machine") which you can then use for direct validation, or as steps in validating more complex specifications.

## Quick Start

The fastest way to try running parts of the validation suite is against an existing cloud service, such as AWS. This can be run by setting up your environment with your AWS keys and running a simple test, as follows:

### Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python package manager)

Install:

```bash
git clone https://github.com/NVIDIA/ISV-NCP-Validation-Suite.git
cd ISV-NCP-Validation-Suite
uv sync
```

Configure credentials:

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_REGION=...
export AWS_SESSION_TOKEN=...  # only required for temporary/SSO credentials
```

Execution:

```bash
$ uv run isvctl test run -f isvctl/configs/providers/aws/control-plane.yaml
Loaded configuration (1 import).
Validating configuration...

Running phases: ['setup', 'test', 'teardown']
... [~80 lines abridged]
------------------------------------------------------------
[PASS] All phases completed successfully
```

## Running against your own platform

Start from the **my-isv living example** — a set of provider-agnostic
template stubs that pass all validations under `ISVCTL_DEMO_MODE=1` and
error out with "Not implemented" otherwise:

```bash
# See the full pipeline run end-to-end in demo mode (~10s, no cloud)
make demo-test

# Copy the scaffolding for your platform and implement each stub
cp -r isvctl/configs/stubs/my-isv/ isvctl/configs/stubs/acme/
cp -r isvctl/configs/providers/my-isv/ isvctl/configs/providers/acme/
# Repoint providers/acme/*.yaml at stubs/acme/ and fill in the TODO blocks
uv run isvctl test run -f isvctl/configs/providers/acme/vm.yaml
```

Templates are available for: [IAM](isvctl/configs/tests/iam.yaml) | [Network](isvctl/configs/tests/network.yaml) | [VM](isvctl/configs/tests/vm.yaml) | [Bare Metal](isvctl/configs/tests/bare_metal.yaml) | [Kubernetes](isvctl/configs/tests/k8s.yaml) | [Control Plane](isvctl/configs/tests/control-plane.yaml) | [Image Registry](isvctl/configs/tests/image-registry.yaml)

See the [Templates README](isvctl/configs/tests/README.md) for the full guide, and the [AWS Reference Implementation](docs/references/aws.md) as a working example.

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

See [Contributing](CONTRIBUTING.md) for development setup and guidelines.

## Environment Variables

| Variable | Description |
| -------- | ----------- |
| `ISV_SERVICE_ENDPOINT` | Required for ISV Lab Service uploads |
| `ISV_SSA_ISSUER` | Required for ISV Lab Service uploads |
| `ISV_CLIENT_ID` | Required for ISV Lab Service uploads |
| `ISV_CLIENT_SECRET` | Required for ISV Lab Service uploads |
| `NGC_API_KEY` | Required for NIM model benchmarks |

## Security

Report vulnerabilities via the [NVIDIA Security Vulnerability Submission Form](https://www.nvidia.com/object/submit-security-vulnerability.html) or email psirt@nvidia.com. **Do not open a public GitHub issue for security vulnerabilities.** See [SECURITY.md](SECURITY.md) for details.

## License

This project is licensed under the [Apache License 2.0](LICENSE).

This project will download and install additional third-party open source software projects. Review the license terms of these open source projects before use.
