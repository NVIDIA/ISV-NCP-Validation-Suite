# isvtest

Validation framework for NVIDIA ISV Lab environments.

> **Note:** For cluster validation, use **`isvctl`** - the unified controller tool.
> `isvtest` is the internal validation engine used by `isvctl`.

## Quick Start

```bash
# From workspace root
uv sync
uv run isvctl test run -f isvctl/configs/tests/k8s.yaml
```

## Documentation

See [docs/packages/isvtest.md](../docs/packages/isvtest.md) for full documentation.

## Related

- [Local Development](../docs/guides/local-development.md)
