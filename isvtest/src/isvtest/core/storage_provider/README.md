# storage_provider

Python contract between [`isvtest`](../../../../) acceptance tests and
provider-implemented storage backends. Each provider authors one Python file per
storage backend that subclasses `Implementation`; `isvtest` imports the file,
calls `build_api()`, and drives the storage acceptance tests against the
provider's real backend — no Kubernetes, sidecar, or REST endpoint required.

|                              |                                                                                                       |
| ---                          | ---                                                                                                   |
| **Source**                   | [`api.py`](./api.py) (contract) · [`mock.py`](./mock.py) (reference impl) · [`loader.py`](./loader.py) (shim discovery) |
| **Contract reference**       | Per-method input/output, error conditions, and capability/qualifier semantics live as docstrings in [`api.py`](./api.py) |
| **Manifest schema**          | [`isvctl/schemas/storage-provider-manifest.schema.json`](../../../../../isvctl/schemas/storage-provider-manifest.schema.json) |                     |

## Quickstart

Providers author one Python file per backend:

```python
# api.py — the file you ship per backend
from isvtest.core.storage_provider import (
    API_VERSION,
    Implementation,
    ProviderProperties,
    StorageProvider,
    VersionMetadata,
    new_implementation,
)

# Static identity declaration. Which optional surfaces are *supported* is
# detected from the methods you override below (and cross-checked against the
# provider manifest, the contract).
_CORE = ProviderProperties(
    provider_namespace="my-backend.example.com",
    provider_id="my-backend",
    provider_metadata=VersionMetadata(
        vendor_name="<your org>",
        name="My Backend",
        version="1.0.0",
    ),
    sdk_version=API_VERSION,
    storage_type="file",
    storage_protocols=["nfsv4"],
)


class MyStorageApi(Implementation):
    def health_check(self) -> None: ...
    def get_tenant_quota(self, req): ...
    def list_volumes(self, req): ...
    # ... see api.py for the full surface (every method takes a request object).
    # To opt OUT of a surface, simply do not define its method.


def build_api() -> StorageProvider:
    return new_implementation(core=_CORE, impl=MyStorageApi(), default_tenant="...")
```

`isvtest` discovers `MyStorageApi` via a provider manifest YAML (the blank
template and a fully-populated example ship under
`isvctl/configs/providers/my-isv/config/`; the field-by-field reference is
[`storage-provider-manifest.schema.json`](../../../../../isvctl/schemas/storage-provider-manifest.schema.json))
and drives the acceptance tests against it.

## What ships

| Path                                | What it does                                                                                                                       |
| ---                                 | ---                                                                                                                                |
| [`api.py`](./api.py)                | `StorageProvider` ABC + `Implementation` / `new_implementation()`, frozen-dataclass DTOs (`Volume`, `Tenant`, `DirectoryQuota`, `UserQuota`, `ProviderProperties`, …), error taxonomy |
| [`mock.py`](./mock.py)              | In-memory `MockStorageApi` reference implementation used by the unit tests                                                         |
| [`loader.py`](./loader.py)          | Loads a provider-authored shim module from disk (bare-metal) or ConfigMap (managed K8s)                                            |

## Tests

Unit tests for the contract package itself live alongside the source in
[`tests/`](./tests/) — pure tests of the ABC surface, the in-memory mock,
and the loader. Providers are not required to run them, but may consult them
as living documentation of the contract.

```bash
uv run pytest isvtest/src/isvtest/core/storage_provider/tests/test_api.py
uv run pytest isvtest/src/isvtest/core/storage_provider/tests/test_mock.py
uv run pytest isvtest/src/isvtest/core/storage_provider/tests/test_loader.py
```

Tests for the isvtest-internal manifest registry (`isvtest.core.storage`)
and the validation that drives the acceptance tests
(`StorageProviderApiCheck`) live with the rest of the framework tests
under `isvtest/tests/`.

## License

Apache-2.0. See the repository [`LICENSE`](../../../../../LICENSE) file.
