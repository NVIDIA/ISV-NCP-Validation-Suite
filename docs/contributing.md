# Contributing

Guidelines for contributing to NVIDIA ISV NCP Validation Suite.

## Getting Started

### Prerequisites

- Linux (Ubuntu) or WSL2
- Git

### Install uv

Install `uv`, a fast Python package manager (replaces `pip` or `poetry`):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Restart your terminal after installation. Alternative installation methods are available in the [uv documentation](https://docs.astral.sh/uv/getting-started/installation/).

### Clone and Setup

```bash
# Clone the repo
git clone https://github.com/NVIDIA/ISV-NCP-Validation-Suite.git
cd ISV-NCP-Validation-Suite

# Install dependencies
uv sync

# Install pre-commit hooks
uvx pre-commit install
```

## Development

This is a monorepo containing multiple packages: `isvctl`, `isvreporter`, and `isvtest`.

### Common Tasks

We provide a Makefile at the root for common development tasks across all packages:

```bash
make help          # Show all available targets
make pre-commit    # Run pre-commit on all packages
make test          # Run tests for all packages
make build         # Build all packages
make lint          # Run linting on all packages
make format        # Format code on all packages
make clean         # Clean build artifacts
```

### Per-Package Development

To work on a specific package:

```bash
cd isvtest  # or isvctl, isvreporter
uv sync                    # Install dependencies
uvx pre-commit run -a      # Run pre-commit
uv run pytest -m unit      # Run unit tests
uv build                   # Build package
```

### Running Tools

```bash
# Run isvctl
uv run isvctl --help

# Run isvtest directly
uv run isvtest --help

# Run isvreporter
uv run isvreporter --help
```

### Building Wheels

Build distributable wheel packages:

```bash
uv build isvctl/ -o dist
uv build isvtest/ -o dist
uv build isvreporter/ -o dist
# Wheels are output to ./dist/
```

## Code Quality

### Pre-commit Hooks

Pre-commit hooks run automatically on commit. To run manually:

```bash
uvx pre-commit run -a
```

### Linting and Formatting

We use `ruff` for linting and formatting:

```bash
# Lint
uvx ruff check --fix

# Format
uvx ruff format
```

### Type Checking

All code includes type annotations and is checked with pyright:

```bash
uvx pyright
```

## Testing

### Unit Tests

```bash
# Run all tests
make test

# Run tests for a specific package
uv --directory=isvtest run pytest tests/ -v
uv --directory=isvctl run pytest -v
uv --directory=isvreporter run pytest -v
```

### Integration Tests

Integration tests require access to a real cluster:

```bash
# Run K8s integration tests (requires kubectl access)
uv run isvctl test run -f isvctl/configs/tests/k8s.yaml

# Run with MicroK8s locally
uv run isvctl test run -f isvctl/configs/providers/microk8s.yaml
```

See [Local Development Guide](guides/local-development.md) for MicroK8s setup.

## Project Structure

```text
ISV-NCP-Validation-Suite/
├── isvctl/           # Controller package
│   ├── configs/      # Example config files
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

## Releasing

### Version Bumping

All packages share a single version. The canonical version lives in each package's `pyproject.toml` and is read at runtime via `importlib.metadata`.

To bump the version, use the bump script:

```bash
# Bump using keywords (increments from the latest git tag)
python scripts/bump-version.py patch          # 0.4.2 -> 0.4.3 (alias: fix)
python scripts/bump-version.py minor          # 0.4.2 -> 0.5.0 (alias: feat)
python scripts/bump-version.py major          # 0.4.2 -> 1.0.0

# Or set an explicit version
python scripts/bump-version.py 1.2.3

# Pre-release versions are also supported
python scripts/bump-version.py 1.0.0-rc.1
```

The script will:

1. Show the current version (from the latest git tag) and the proposed new version
2. Warn about major changes, skipped versions, or other anomalies
3. Ask for confirmation before writing
4. Update all 4 `pyproject.toml` files (root + isvctl + isvtest + isvreporter)
5. Run `uv lock` to sync the lockfile

### Signing Your Work

- We require that all contributors "sign-off" on their commits. This certifies that the contribution is your original work, or you have rights to submit it under the same license, or a compatible license.

  - Any contribution which contains commits that are not Signed-Off will not be accepted.

- To sign off on a commit you simply use the `--signoff` (or `-s`) option when committing your changes:

  ```bash
    git commit -s -m "Add cool feature."
  ```

  This will append the following to your commit message:

  ```text
    Signed-off-by: Your Name <your@email.com>
  ```

- Full text of the DCO:

  ```text
    Developer Certificate of Origin
    Version 1.1

    Copyright (C) 2004, 2006 The Linux Foundation and its contributors.
    1 Letterman Drive
    Suite D4700
    San Francisco, CA, 94129

    Everyone is permitted to copy and distribute verbatim copies of this license document, but changing it is not allowed.
  ```

  ```text
    Developer's Certificate of Origin 1.1

    By making a contribution to this project, I certify that:

    (a) The contribution was created in whole or in part by me and I have the right to submit it under the open source license indicated in the file; or

    (b) The contribution is based upon previous work that, to the best of my knowledge, is covered under an appropriate open source license and I have the right under that license to submit that work with modifications, whether created in whole or in part by me, under the same open source license (unless I am permitted to submit under a different license), as indicated in the file; or

    (c) The contribution was provided directly to me by some other person who certified (a), (b) or (c) and I have not modified it.

    (d) I understand and agree that this project and the contribution are public and that a record of the contribution (including all personal information I submit with it, including my sign-off) is maintained indefinitely and may be redistributed consistent with this project or the open source license(s) involved.
  ```

### Pull Requests

Developer workflow for code contributions is as follows:

1. Developers must first [fork](https://help.github.com/en/articles/fork-a-repo) the [upstream](https://github.com/NVIDIA/ISV-NCP-Validation-Suite) ISV NCP Validation Suite repository.

2. Git clone the forked repository and push changes to the personal fork.

  ```bash
    git clone https://github.com/YOUR_USERNAME/YOUR_FORK.git ISV-NCP-Validation-Suite
    # Checkout the targeted branch and commit changes
    # Push the commits to a branch on the fork (remote).
    git push -u origin <local-branch>:<remote-branch>
  ```

3. Once the code changes are staged on the fork and ready for review, a [Pull Request](https://help.github.com/en/articles/about-pull-requests) (PR) can be [requested](https://help.github.com/en/articles/creating-a-pull-request) to merge the changes from a branch of the fork into a selected branch of upstream.
  - Exercise caution when selecting the source and target branches for the PR.
  - Creation of a PR creation kicks off the code review process.
  - Assign reviewer as `NCP ISV Lab Maintainer` and at least one engineer will review the PR.
  - Pipeline will be trigger manually by reviewer

### Creating a Release Tag

> Noted the steps will be executed by `NCP ISV Lab Maintainer` once the PR merged and plan to release.

After bumping, open a PR, review, and merge. Then the repo maintainers will create new tag in following procedure:

1. Go to **Actions** > **Create version tag** in GitHub
2. Enter the version (e.g. `1.0.0`, without leading `v`)
3. The workflow verifies all `pyproject.toml` files match, then creates and pushes `v1.0.0`

You can also verify locally before triggering the workflow:

```bash
python scripts/bump-version.py --check 1.0.0
```

## Advanced

### Minimal Installation

To install without dev dependencies:

```bash
uv sync --no-dev
```

### Regenerating Schemas

To regenerate JSON schemas from Pydantic models:

```bash
uv --directory=isvctl run python scripts/check_schemas.py --generate
```

## Related Documentation

- [Getting Started](getting-started.md) - Installation and usage
- [isvctl Reference](packages/isvctl.md) - Controller documentation
- [isvtest Reference](packages/isvtest.md) - Validation framework
- [isvreporter Reference](packages/isvreporter.md) - Reporter documentation
