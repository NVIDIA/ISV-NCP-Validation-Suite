# isvctl

Unified controller for ISV Lab cluster lifecycle orchestration.

## Quick Start

```bash
# From workspace root
uv sync
uv run isvctl test run -f isvctl/configs/k8s.yaml

# View documentation
uv run isvctl docs
uv run isvctl docs -t getting-started        # view a specific topic

# List all validation tests by category
uv run isvctl docs tests
uv run isvctl docs tests -m kubernetes                   # filter by marker
uv run isvctl docs tests -f isvctl/configs/k8s.yaml      # show config test instances
uv run isvctl docs tests -i StepSuccessCheck             # detailed info for a test
```

## Documentation

See [docs/packages/isvctl.md](../docs/packages/isvctl.md) for full documentation.

## Related

- [Configuration Guide](../docs/guides/configuration.md)
- [Remote Deployment](../docs/guides/remote-deployment.md)
- [Validation Templates](configs/templates/README.md) - Provider-agnostic templates for partner handoff (IAM, etc.)
