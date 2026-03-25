<!--
SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# Contributing to ISV NCP Validation Suite

Thank you for your interest in contributing! This project is a **Python monorepo** with three interdependent packages (`isvctl`, `isvtest`, `isvreporter`) managed as a [uv](https://docs.astral.sh/uv/) workspace. It orchestrates GPU cluster validation across Kubernetes, Slurm, and bare-metal environments, so even small changes can have cross-package effects. Please read through this guide before opening a pull request.

## Table of Contents

- [Issues Management] (#issues-management)
- [About This Codebase](#about-this-codebase)
- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development](#development)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)
- [Developer Certificate of Origin (DCO)](#developer-certificate-of-origin-dco)
- [Releasing](#releasing)

## Issues Management

Read the README.md to understand the project
Check existing issues to avoid duplicates
Browse discussions for questions
Review the security policy for security-related contributions

Ways to contribute:

🐛 Report bugs via GitHub issues
💡 Suggest features through feature requests
📝 Improve documentation
🧪 Add tests to increase coverage
🔧 Fix issues with code contributions
💬 Help others in discussions

Reporting Issues
When reporting issues:

Use the issue templates when available
Provide clear reproduction steps
Include environment details (OS, Kubernetes version, etc.)
Add relevant logs or error messages
Search existing issues first to avoid duplicates

## About This Codebase

ISV NCP Validation Suite is a monorepo with three packages:

| Package | Purpose |
|---------|---------|
| **isvctl** | CLI controller — orchestrates setup, test, and teardown phases via step-based configs |
| **isvtest** | Validation engine — pytest-based framework with dynamic test discovery |
| **isvreporter** | Results reporter — uploads test results to the ISV Lab Service API |

Changes often span packages. For example, adding a new validation involves `isvtest` (test class), `isvctl` (config schema / stubs), and possibly `isvreporter` (result format). Please consider cross-package impact when contributing.

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior to GitHub_Conduct@nvidia.com.

## Getting Started

### Prerequisites

- Linux (Ubuntu) or WSL2
- Git
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python package manager)

### Clone and Setup

```bash
git clone https://github.com/NVIDIA/ISV-NCP-Validation-Suite.git
cd ISV-NCP-Validation-Suite
uv sync
uvx pre-commit install
```

## Development

### Common Tasks

```bash
make help          # Show all available targets
make test          # Run tests for all packages
make lint          # Run linting on all packages
make format        # Format code on all packages
make pre-commit    # Run pre-commit on all packages
make build         # Build all packages
make clean         # Clean build artifacts
```

### Per-Package Development

```bash
cd isvtest  # or isvctl, isvreporter
uv sync
uvx pre-commit run -a
uv run pytest -m unit
uv build
```

### Running Tools

```bash
uv run isvctl --help
uv run isvtest --help
uv run isvreporter --help
```

### Code Quality

We use `ruff` for linting and formatting, and `pyright` for type checking. All code must include type annotations and docstrings (PEP 257).

```bash
uvx ruff check --fix    # Lint
uvx ruff format          # Format
uvx pyright              # Type check
```

Pre-commit hooks run automatically on commit. To run manually:

```bash
uvx pre-commit run -a
```

## Testing

All CI checks must pass before a PR can be merged.

### Unit Tests

```bash
# All packages
make test

# Specific package
uv --directory=isvtest run pytest tests/ -v
uv --directory=isvctl run pytest -v
uv --directory=isvreporter run pytest -v
```

### Integration Tests

Integration tests require access to a real cluster:

```bash
uv run isvctl test run -f isvctl/configs/tests/k8s.yaml
uv run isvctl test run -f isvctl/configs/providers/microk8s.yaml
```

See the [Local Development Guide](docs/guides/local-development.md) for MicroK8s setup.

## Pull Request Process

1. **Fork** the [upstream repository](https://github.com/NVIDIA/ISV-NCP-Validation-Suite) and create a branch from `main`.
2. **Make your changes** following the coding guidelines above.
3. **Run the full check suite** before opening the PR:

   ```bash
   make test && make lint
   ```

4. **Sign off all commits** (see [DCO](#developer-certificate-of-origin-dco) below).
5. **Open a pull request** with a clear description of what changed and why.

### PR Guidelines

- Provide a clear description of the problem and solution.
- Reference any related issues.
- Keep pull requests focused on a single change.
- Ensure all CI checks pass before requesting review.
- Be responsive to feedback and code review comments.
- Assign reviewer as `NCP ISV Lab Maintainer` — at least one engineer will review the PR.

## Developer Certificate of Origin (DCO)

This project requires the [Developer Certificate of Origin](https://developercertificate.org/) (DCO) process for all contributions. The DCO is a lightweight way for contributors to certify that they wrote or otherwise have the right to submit the code they are contributing.

### Signing Your Commits

Add a `Signed-off-by` line to every commit using the `-s` flag:

```bash
git commit -s -m "Your commit message"
```

This appends a line like:

```
Signed-off-by: Your Name <your@email.com>
```

**Tip:** Create a Git alias to always sign off:

```bash
git config --global alias.ci 'commit -s'
# Now use: git ci -m "Your commit message"
```

### Signing Off Multiple Commits

```bash
git rebase --signoff origin/main
```

### DCO Enforcement

All pull requests are automatically checked for DCO compliance via the DCO bot. Pull requests with unsigned commits cannot be merged until all commits are properly signed off.

### Full DCO Text

```
Developer Certificate of Origin
Version 1.1

Copyright (C) 2004, 2006 The Linux Foundation and its contributors.

Everyone is permitted to copy and distribute verbatim copies of this
license document, but changing it is not allowed.


Developer's Certificate of Origin 1.1

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I
    have the right to submit it under the open source license
    indicated in the file; or

(b) The contribution is based upon previous work that, to the best
    of my knowledge, is covered under an appropriate open source
    license and I have the right under that license to submit that
    work with modifications, whether created in whole or in part
    by me, under the same open source license (unless I am
    permitted to submit under a different license), as indicated
    in the file; or

(c) The contribution was provided directly to me by some other
    person who certified (a), (b) or (c) and I have not modified
    it.

(d) I understand and agree that this project and the contribution
    are public and that a record of the contribution (including all
    personal information I submit with it, including my sign-off) is
    maintained indefinitely and may be redistributed consistent with
    this project or the open source license(s) involved.
```

## Releasing

### Version Bumping

All packages share a single version. To bump:

```bash
python scripts/bump-version.py patch          # 0.4.2 -> 0.4.3
python scripts/bump-version.py minor          # 0.4.2 -> 0.5.0
python scripts/bump-version.py major          # 0.4.2 -> 1.0.0
python scripts/bump-version.py 1.2.3          # Explicit version
```

The script updates all `pyproject.toml` files and runs `uv lock`.

### Creating a Release Tag

After bumping, open a PR, review, and merge. Then the repo maintainers will create a tag:

1. Go to **Actions** > **Create version tag** in GitHub
2. Enter the version (e.g. `1.0.0`, without leading `v`)
3. The workflow verifies all `pyproject.toml` files match, then creates and pushes `v1.0.0`

## Project Structure

```text
ISV-NCP-Validation-Suite/
├── isvctl/           # Controller package
│   ├── configs/      # Config files and stub scripts
│   ├── src/isvctl/   # Source code
│   └── tests/        # Unit tests
├── isvtest/          # Validation framework
│   ├── src/isvtest/  # Source code
│   └── tests/        # Unit tests
├── isvreporter/      # Reporter package
│   ├── src/isvreporter/
│   └── tests/
└── docs/             # Documentation
```

## Related Documentation

- [Getting Started](docs/getting-started.md) — Installation and usage
- [Configuration](docs/guides/configuration.md) — Config file format and options
- [Local Development](docs/guides/local-development.md) — MicroK8s setup for local testing

## License

By contributing to this project, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).


## Issues Management

Read the README.md to understand the project
Check existing issues to avoid duplicates
Browse discussions for questions
Review the security policy for security-related contributions
How to Contribute
Ways to contribute:

🐛 Report bugs via GitHub issues
💡 Suggest features through feature requests
📝 Improve documentation
🧪 Add tests to increase coverage
🔧 Fix issues with code contributions
💬 Help others in discussions
Reporting Issues
When reporting issues:

Use the issue templates when available
Provide clear reproduction steps
Include environment details (OS, Kubernetes version, etc.)
Add relevant logs or error messages
Search existing issues first to avoid duplicates

Community Guidelines
Be respectful and inclusive in all interactions
Follow the Code of Conduct
Help maintain a welcoming environment
Focus on constructive feedback in reviews

