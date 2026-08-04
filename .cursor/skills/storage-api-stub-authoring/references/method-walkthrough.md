# Method walkthrough

Implement **in this order**. After each method, run the probe in Phase 4.

Subtests map to `StorageProviderApiCheck` (`isvtest/validations/storage_provider.py`):

| Method | Subtest | Requirement |
| ------ | ------- | ----------- |
| `health_check` | `api-authentication[<name>]` | Authenticated round-trip; `AuthenticationError` on 401/403 |
| `create_volume` or `list_volumes` | `volume-provisioning[<name>]` | Create+delete path OR CSI fallback with ≥1 volume |
| `get_tenant_quota` | `tenant-quota[<name>]` | `hard_limit_bytes > 0` |

---

## 0. `build_api()` factory

```python
def build_api() -> StorageApi:
    return MyStorageApi()
```

Module-level, no arguments. Loader: `isvtest.core.storage_provider.build_api_from_path`.

**Target file:** `isvctl/configs/providers/my-isv/scripts/storage/api.py` — replace
each `TODO` block in the existing `MyStorageApi` class; do not copy to a new path.

---

## 1. `__init__` — connection setup

**Questions:**

- Which env vars hold endpoint, credentials, default tenant, storage root path?
- Should missing required env vars fail fast at construction or first call?
- Multi-provider manifest: one shim class with env vars, or separate modules per entry?

**Implement:**

- Read config from env (Phase 1a) or mounted file path (future ConfigMap)
- Build SDK client / HTTP session
- Set `self._default_tenant` from env or leave `None` for required `tenant_id` arg

**Probe:** Import module without calling cloud APIs (syntax + env validation only).

---

## 2. `properties()` — identity + L2 qualifiers

**Questions:**

- `provider_name`, `provider_implementor`, `provider_storage_type` (`file` | `block`)?
- `provider_protocol` — `nfsv4`, `lustre`, `ext4`, …?
- Directory/user quota supported? (declared in the **manifest**, not here)

**Implement:** Return `ProviderProperties(...)` carrying identity and any L2
qualifiers (via the `capability_qualifiers()` hook). `properties()` does *not*
declare which surfaces are supported — that lives in the manifest's
`capabilities:` block and is verified by runtime probing.

**Probe:** `api.properties().provider_name` returns expected string.

---

## 3. `health_check()`

**Questions:**

- What is the **smallest authenticated call** that proves creds work?
- What HTTP status / error code → `AuthenticationError`?
- Transient errors — raise generic exception (fails subtest) vs retry?

**Implement:**

- One round-trip to management API
- Return `None` on success
- Raise `AuthenticationError` for auth failures only

**Reference calls:**

- AWS: `servicequotas:GetServiceQuota` (fsx service code)
- VAST: `GET /api/quotas/`

**Probe:** CLI equivalent + `probe_shim.py` authentication line.

---

## 4. `get_tenant_quota()`

**Questions:**

- How is tenant resolved (`tenant_id` arg vs default)?
- Source of `hard_limit_bytes` — quota API, sum of children, service limit?
- Source of `used_bytes` — allocation sum, metered usage, effective capacity?
- Display `name` for tenant?

**Implement:**

```python
return TenantQuota(
    tenant_id=resolved,
    hard_limit_bytes=int,  # MUST be > 0
    used_bytes=int,
    name=str | None,
)
```

**Probe:** `probe_shim.py` tenant-quota line; verify `hard_limit_bytes > 0`.

---

## 5. Volume lifecycle

### Branch A: CSI owns lifecycle (AWS, VAST, WEKA)

**Questions:**

- How to list existing volumes/PVC-backed exports?
- How to map backend record → `Volume` dataclass?
- Populate `Volume.csi` (`driver`, `volume_handle`) and/or `Volume.mount` (`source`)?
- What exact volume-handle format does the CSI driver put on PVs?

**Implement:**

- `create_volume` / `delete_volume` → `raise NotSupportedError(...)`
- `list_volumes` → yield `Volume` objects for tenant-scoped inventory
- Honor `ids` filter; `tag_filters` if backend supports tags (else ignore safely)

**Reference:**

- AWS: `fsx:DescribeFileSystems` (LUSTRE only)
- VAST: child directory quotas under `VAST_STORAGE_PATH`
- WEKA: one filesystem per `weka/v2/<fs>` volume handle

**Probe:** `list_volumes()` count ≥ 1 (user may need to create PVC first).

### Branch B: API owns lifecycle

**Questions:**

- Create API parameters for name, size, volume_type, tags?
- Sync or async creation — initial `state` `creating` vs `available`?
- Delete idempotent?

**Implement:**

- `create_volume` — return `Volume` with `state` in `creating` | `available`
- `delete_volume` — clean up; warn if create without delete (check logs)
- Tag with `isvtest-run-id` and `provider` (check passes these)

**Probe:** `probe_shim.py` with `--exercise-create` (if script supports) or manual call.

---

## 6. `list_volumes()` — always required for CSI path

**Questions:**

- Filter by `ids` — exact match on volume id?
- `tag_filters` — AND semantics per `TagFilter`?
- Foreign tenant volumes — must never appear even if filters would match

**Implement:** Generator/`Iterable` of `Volume` with correct `tenant_id`, `size_bytes`, `state`.

---

## 7. Optional methods

Leave as base-class `NotSupportedError` (or an explicit raising stub) unless
needed:

- `list_tenants`, `get_tenant`
- `list/get/set/delete_directory_quota`
- `list/get/set/delete_user_quota`

When you implement any of these, declare the matching surface supported
(`native`) in the **manifest** — that is what validation probes. Surfaces you
leave as raising stubs stay `none`.

---

## Volume dataclass checklist

Each `Volume` should set when known:

- `id`, `name`, `tenant_id`, `size_bytes`, `state`, `volume_type`
- `csi.driver`, `csi.volume_handle` — for K8s CSI backends
- `mount.source` — NFS mount spec (VAST: `{vip_pool}:{path}`)
- `tags` — if backend supports metadata
