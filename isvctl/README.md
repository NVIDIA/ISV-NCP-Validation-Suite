# isvctl

Unified controller for ISV Lab cluster lifecycle orchestration.

## Quick Start

```bash
# From workspace root
uv sync
uv run isvctl test run -f isvctl/configs/k8s.yaml

# View documentation
uv run isvctl docs
```

## Documentation

See [docs/packages/isvctl.md](../docs/packages/isvctl.md) for full documentation.

## Related

- [Configuration Guide](../docs/guides/configuration.md)
- [Remote Deployment](../docs/guides/remote-deployment.md)
- [Validation Templates](configs/templates/README.md) - Provider-agnostic templates for partner handoff (IAM, etc.)
