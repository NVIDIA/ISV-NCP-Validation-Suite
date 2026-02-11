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
uv run isvctl test run -f isvctl/configs/k8s.yaml

# Run with MicroK8s locally
uv run isvctl test run -f isvctl/configs/microk8s.yaml
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
