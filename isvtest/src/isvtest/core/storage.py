# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Provider manifest parsing + registry for the storage shim.

The manifest mirrors the upstream StorageProvider package manifest in how it
declares storage-api values and capabilities:

* package-level ``namespace`` + ``vendor`` (the registration domain and vendor
  metadata) and an optional package-wide ``default_capabilities`` policy;
* per-provider ``provider: {name, description, type, protocols, version}`` and
  optional ``backend`` metadata (the static facet of ``ProviderProperties``);
* a hierarchical ``capabilities:`` block using ``native`` | ``default`` | ``none``
  with group cascade and most-specific-wins resolution (lowered here into a flat
  ``cap_id -> expected-supported`` map the contract check asserts against);
* optional L2 ``capability_qualifiers`` (semantic facts like ``idAssignment``).

The same YAML file is consumed on disk (bare-metal mode) and inside a ConfigMap
(K8s); there is no K8s API call in the parser itself.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

import yaml

from isvtest.core.storage_provider import (
    CAP_DIRECTORY_QUOTA_DELETE,
    CAP_DIRECTORY_QUOTA_GET,
    CAP_DIRECTORY_QUOTA_LIST,
    CAP_DIRECTORY_QUOTA_SET,
    CAP_TENANT_GET,
    CAP_TENANT_GET_QUOTA,
    CAP_TENANT_LIST,
    CAP_TENANT_LIST_QUOTAS,
    CAP_USER_QUOTA_DELETE,
    CAP_USER_QUOTA_GET,
    CAP_USER_QUOTA_LIST,
    CAP_USER_QUOTA_SET,
    CAP_VOLUME_CREATE,
    CAP_VOLUME_DELETE,
    CAP_VOLUME_GET,
    CAP_VOLUME_LIST,
    CAPABILITY_IDS,
    ShimLoadError,
    StorageProvider,
    VolumeType,
    build_api_from_path,
)

_logger = logging.getLogger(__name__)

SUPPORTED_SCHEMA_VERSIONS: tuple[str, ...] = ("v1alpha1", "v1alpha2")
ShimKind = Literal["python", "rest"]
CapabilityDeclaration = Literal["native", "default", "none"]

# Build-manifest capability states. ``native`` and
# ``default`` both yield a serviceable (``supported``) surface; ``none`` opts out.
_CAPABILITY_STATES: tuple[str, ...] = ("native", "default", "none")

# camelCase manifest capability tree -> dotted capability-id leaves. Mirrors the
# package manifest grouping (tenantManagement / volumeManagement / quotaManagement
# with directory + user quota subgroups). Leaf values are the registry ids the
# contract check asserts against; nested dicts are groups.
_CAPABILITY_TREE: dict[str, Any] = {
    "tenantManagement": {
        "list": CAP_TENANT_LIST,
        "get": CAP_TENANT_GET,
        "getQuota": CAP_TENANT_GET_QUOTA,
        "listQuotas": CAP_TENANT_LIST_QUOTAS,
    },
    "volumeManagement": {
        "list": CAP_VOLUME_LIST,
        "get": CAP_VOLUME_GET,
        "create": CAP_VOLUME_CREATE,
        "delete": CAP_VOLUME_DELETE,
    },
    "quotaManagement": {
        "directory": {
            "list": CAP_DIRECTORY_QUOTA_LIST,
            "get": CAP_DIRECTORY_QUOTA_GET,
            "set": CAP_DIRECTORY_QUOTA_SET,
            "delete": CAP_DIRECTORY_QUOTA_DELETE,
        },
        "user": {
            "list": CAP_USER_QUOTA_LIST,
            "get": CAP_USER_QUOTA_GET,
            "set": CAP_USER_QUOTA_SET,
            "delete": CAP_USER_QUOTA_DELETE,
        },
    },
}


class ManifestError(Exception):
    """The provider manifest is missing, malformed, or violates the schema."""


@dataclass(frozen=True)
class Provider:
    """Manifest entry + the live ``StorageProvider`` client (when a shim is loaded).

    The identity fields mirror the static facet of ``ProviderProperties``:
    ``provider_namespace`` + ``provider_id`` form the registration key
    ``<namespace>/<id>``; ``storage_protocols`` is the wire-protocol list;
    ``provider_version`` is the implementor semver. ``expected_capabilities``
    is the lowered ``cap_id -> supported?`` map and ``capability_qualifiers`` the
    optional L2 semantic facts; both are cross-checked against the running shim.
    """

    name: str
    volume_type: VolumeType
    tenant_id: str | None = None
    provider_namespace: str | None = None
    provider_id: str | None = None
    provider_version: str | None = None
    storage_protocols: tuple[str, ...] = ()
    vendor: Mapping[str, Any] = field(default_factory=dict)
    backend: Mapping[str, Any] = field(default_factory=dict)
    sdk_version: str | None = None
    expected_capabilities: Mapping[str, bool] = field(default_factory=dict)
    capability_states: Mapping[str, CapabilityDeclaration] = field(default_factory=dict)
    capability_qualifiers: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    attributes: Mapping[str, str] = field(default_factory=dict)
    # K8s StorageClass names from an instance config's ``storageClasses`` (empty
    # unless a two-layer instance ``config.yaml`` supplied them).
    storage_classes: tuple[str, ...] = ()
    shim_kind: ShimKind | None = None
    api: StorageProvider | None = None

    @property
    def has_shim(self) -> bool:
        return self.api is not None


def load_provider_registry(config: Mapping[str, Any]) -> list[Provider]:
    """Parse the manifest pointed at by ``config["manifest_path"]`` and load each shim.

    Returns one ``Provider`` per manifest entry. Providers with a
    ``shim.kind: python`` block have ``api`` populated; CSI-only providers and
    ``shim.kind: rest`` entries return with ``api=None``.

    Returns an empty list when ``manifest_path`` is unset / empty so the check
    can skip cleanly on providers that haven't onboarded the shim yet. Raises
    ``ManifestError`` on any other malformed input.
    """
    manifest_path = str(config.get("manifest_path") or "").strip()
    if not manifest_path:
        return []

    path = Path(manifest_path).expanduser()
    if not path.is_file():
        raise ManifestError(f"manifest file not found: {path}")

    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ManifestError(f"failed to parse manifest {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ManifestError(f"manifest {path} must be a YAML mapping at the top level")

    schema_version = raw.get("schema_version")
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ManifestError(
            f"manifest {path}: schema_version={schema_version!r} not supported "
            f"(expected one of {list(SUPPORTED_SCHEMA_VERSIONS)})"
        )

    providers_raw = raw.get("providers")
    if not isinstance(providers_raw, list):
        raise ManifestError(f"manifest {path}: providers must be a list (got {type(providers_raw).__name__})")

    # Package-level identity / policy (mirrors the package manifest). All optional.
    # The camelCase key (``defaultCapabilities``) mirrors the upstream package
    # manifest; the snake_case ``default_capabilities`` is accepted as a
    # backward-compatible fallback for pre-existing manifests.
    package_namespace = raw.get("namespace")
    package_vendor = _coerce_mapping(raw.get("vendor"), field_name="vendor")
    default_caps_key = "defaultCapabilities" if "defaultCapabilities" in raw else "default_capabilities"
    package_default_caps = _coerce_mapping(raw.get(default_caps_key), field_name=default_caps_key)

    manifest_dir = path.parent
    providers: list[Provider] = []
    seen_names: set[str] = set()
    for index, entry in enumerate(providers_raw):
        if not isinstance(entry, dict):
            raise ManifestError(f"manifest {path}: providers[{index}] must be a mapping")
        provider = _build_provider(
            entry,
            index=index,
            manifest_dir=manifest_dir,
            package_namespace=package_namespace,
            package_vendor=package_vendor,
            package_default_caps=package_default_caps,
        )
        if provider.name in seen_names:
            raise ManifestError(f"manifest {path}: duplicate provider name {provider.name!r}")
        seen_names.add(provider.name)
        providers.append(provider)

    # Optional second layer: an nv-storage-style per-instance config that
    # overrides defaultTenant / storageClasses / capabilities on top of the
    # manifest (the first layer). Consume-only: the shim still reads its own
    # backend config/credentials at build_api() time, so backend.config and
    # secrets are not imported here.
    instance = _load_instance_config(config, path)
    if instance is not None:
        providers = [_apply_instance_config(p, instance) for p in providers]
    return providers


def _build_provider(
    entry: Mapping[str, Any],
    *,
    index: int,
    manifest_dir: Path,
    package_namespace: Any,
    package_vendor: Mapping[str, Any],
    package_default_caps: Mapping[str, Any],
) -> Provider:
    # `provider:` block mirrors the package manifest providers.<id>.provider. The
    # legacy v1alpha2 `identity` block is still accepted as a fallback source.
    provider_block = _coerce_mapping(entry.get("provider"), field_name=f"providers[{index}].provider")
    identity = _coerce_mapping(entry.get("identity"), field_name=f"providers[{index}].identity")
    identity_provider = _coerce_mapping(identity.get("provider"), field_name=f"providers[{index}].identity.provider")

    # ``name`` falls back to ``id`` then identity.provider.id.
    name = entry.get("name")
    if not isinstance(name, str) or not name:
        candidate = entry.get("id") or identity_provider.get("id")
        name = candidate if isinstance(candidate, str) and candidate else None
    if not name:
        raise ManifestError(
            f"providers[{index}]: name (or id / identity.provider.id) is required and must be a non-empty string"
        )

    # ``type`` falls back to provider.type then identity.storage_type; accept the
    # uppercase FILE/BLOCK proto forms.
    raw_type = entry.get("type")
    if raw_type is None:
        raw_type = provider_block.get("type")
    if raw_type is None:
        raw_type = identity.get("storage_type")
    if isinstance(raw_type, str):
        raw_type = raw_type.lower()
    if raw_type not in ("file", "block"):
        raise ManifestError(
            f"providers[{index}] ({name!r}): type must be 'file' or 'block' "
            f"(set providers[].type, provider.type, or identity.storage_type; got {raw_type!r})"
        )

    tenant_id_raw = entry.get("tenant_id")
    if tenant_id_raw is not None and not isinstance(tenant_id_raw, str | int):
        raise ManifestError(f"providers[{index}] ({name!r}): tenant_id must be a string or int")
    tenant_id = str(tenant_id_raw) if tenant_id_raw is not None else None

    # Identity scalars (mirror ProviderProperties). namespace / id / version /
    # protocols are sourced from the provider block first, then identity, then
    # the package namespace.
    provider_namespace = (
        entry.get("namespace")
        or provider_block.get("namespace")
        or identity_provider.get("namespace")
        or identity_provider.get("domain")  # legacy field name
        or package_namespace
    )
    provider_id = entry.get("id") or provider_block.get("id") or identity_provider.get("id") or name
    provider_version = provider_block.get("version") or identity_provider.get("version")
    storage_protocols = _coerce_protocols(
        entry.get("protocols")
        or provider_block.get("protocols")
        or identity.get("storage_protocols")
        or identity.get("storage_protocol"),
        field_name=f"providers[{index}] ({name!r}).protocols",
    )
    sdk_version = entry.get("sdk_version") or identity.get("sdk_version")

    vendor = _coerce_mapping(entry.get("vendor"), field_name=f"providers[{index}] ({name!r}).vendor") or dict(
        package_vendor
    )
    # Fold the human-facing provider name / description into the vendor metadata
    # bag so consumers see the full VersionMetadata-shaped values.
    for key in ("name", "description"):
        if provider_block.get(key) is not None and key not in vendor:
            vendor[key] = provider_block[key]
    backend = _coerce_mapping(
        entry.get("backend") or identity.get("backend"),
        field_name=f"providers[{index}] ({name!r}).backend",
    )

    capability_states = _resolve_capability_states(
        _coerce_mapping(
            entry.get("capabilities"),
            field_name=f"providers[{index}] ({name!r}).capabilities",
        ),
        package_default_caps,
        field_name=f"providers[{index}] ({name!r}).capabilities",
    )
    expected_capabilities = {cap_id: state != "none" for cap_id, state in capability_states.items()}
    capability_qualifiers = _coerce_qualifiers(
        entry.get("capability_qualifiers"),
        field_name=f"providers[{index}] ({name!r}).capability_qualifiers",
    )
    attributes = _coerce_string_mapping(entry.get("attributes"), field_name=f"providers[{index}] ({name!r}).attributes")

    shim_kind, api = _load_shim(entry.get("shim"), name=name, manifest_dir=manifest_dir, attributes=attributes)

    return Provider(
        name=name,
        volume_type=raw_type,
        tenant_id=tenant_id,
        provider_namespace=str(provider_namespace) if provider_namespace else None,
        provider_id=str(provider_id) if provider_id else None,
        provider_version=str(provider_version) if provider_version is not None else None,
        storage_protocols=storage_protocols,
        vendor=vendor,
        backend=backend,
        sdk_version=str(sdk_version) if sdk_version else None,
        expected_capabilities=expected_capabilities,
        capability_states=capability_states,
        capability_qualifiers=capability_qualifiers,
        attributes=attributes,
        shim_kind=shim_kind,
        api=api,
    )


def _load_shim(
    shim_entry: Any,
    *,
    name: str,
    manifest_dir: Path,
    attributes: Mapping[str, str],
) -> tuple[ShimKind | None, StorageProvider | None]:
    if shim_entry is None:
        return None, None
    if not isinstance(shim_entry, dict):
        raise ManifestError(f"provider {name!r}: shim must be a mapping")

    kind = shim_entry.get("kind")
    if kind not in ("python", "rest"):
        raise ManifestError(f"provider {name!r}: shim.kind must be 'python' or 'rest' (got {kind!r})")

    if kind == "rest":
        _logger.info(
            "provider %r declares shim.kind=rest; Phase 1a in-process Python loader skips REST endpoints",
            name,
        )
        return "rest", None

    module = shim_entry.get("module")
    if not isinstance(module, str) or not module:
        raise ManifestError(f"provider {name!r}: shim.module is required for shim.kind=python")
    shim_path = (manifest_dir / module).resolve()
    try:
        api = build_api_from_path(shim_path, attributes=attributes)
    except ShimLoadError as exc:
        raise ManifestError(f"provider {name!r}: failed to load shim {shim_path}: {exc}") from exc
    return "python", api


def _coerce_mapping(value: Any, *, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ManifestError(f"{field_name}: must be a mapping")
    return dict(value)


def _coerce_protocols(value: Any, *, field_name: str) -> tuple[str, ...]:
    """Coerce the wire-protocol declaration to a tuple of strings.

    Accepts a list (the new ``protocols`` shape) or a single scalar (the legacy
    ``storage_protocol`` shape).
    """
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(str(v) for v in value)
    raise ManifestError(f"{field_name}: must be a string or list of strings")


def _resolve_capabilities(
    provider_caps: Mapping[str, Any],
    package_caps: Mapping[str, Any],
    *,
    field_name: str,
) -> dict[str, bool]:
    """Lower the hierarchical capabilities block to ``cap_id -> supported?``."""
    return {
        cap_id: state != "none"
        for cap_id, state in _resolve_capability_states(provider_caps, package_caps, field_name=field_name).items()
    }


def _resolve_capability_states(
    provider_caps: Mapping[str, Any],
    package_caps: Mapping[str, Any],
    *,
    field_name: str,
) -> dict[str, CapabilityDeclaration]:
    """Lower the hierarchical capabilities block to ``cap_id -> native/default/none``.

    Mirrors the package manifest resolution: most-specific wins, the provider block
    overrides the package ``default_capabilities``, and an absent capability with
    no ``default:`` fallback is left undeclared. The boolean
    ``expected_capabilities`` view is derived from this state map for legacy
    contract checks, while validations that need to distinguish backend-native
    behavior can inspect this richer declaration.
    """
    _validate_capability_block(provider_caps, field_name=field_name)
    _validate_capability_block(package_caps, field_name="default_capabilities")
    has_default = "default" in provider_caps or "default" in package_caps

    resolved: dict[str, CapabilityDeclaration] = {}
    for cap_id, path in _capability_leaves():
        state = _lookup_capability(provider_caps, path)
        if state is None:
            state = _lookup_capability(package_caps, path)
        explicit = state is not None
        if state is None:
            state = _default_state(provider_caps, package_caps)
        if state is None:
            continue  # undeclared and no default -> leave unchecked
        # Only record a capability the manifest meaningfully declares: an
        # explicit leaf/group state, or a `default:` fallback.
        if not explicit and not has_default:
            continue
        resolved[cap_id] = state
    return resolved


def _capability_leaves(tree: Any = None, prefix: tuple[str, ...] = ()) -> list[tuple[str, tuple[str, ...]]]:
    """Flatten ``_CAPABILITY_TREE`` to ``(cap_id, manifest_path)`` leaf pairs."""
    if tree is None:
        tree = _CAPABILITY_TREE
    leaves: list[tuple[str, tuple[str, ...]]] = []
    for key, value in tree.items():
        if isinstance(value, dict):
            leaves.extend(_capability_leaves(value, (*prefix, key)))
        else:
            leaves.append((value, (*prefix, key)))
    return leaves


def _lookup_capability(caps: Mapping[str, Any], path: tuple[str, ...]) -> str | None:
    """Return the deepest scalar state along ``path`` in ``caps`` (most specific)."""
    node: Any = caps
    found: str | None = None
    for key in path:
        if not isinstance(node, dict) or key not in node:
            break
        node = node[key]
        if isinstance(node, str):
            found = node
    return found


def _default_state(provider_caps: Mapping[str, Any], package_caps: Mapping[str, Any]) -> str | None:
    for caps in (provider_caps, package_caps):
        value = caps.get("default")
        if isinstance(value, str):
            return value
    return None


def _validate_capability_block(caps: Mapping[str, Any], *, field_name: str, _path: str = "") -> None:
    """Reject capability values that are not native/default/none (or a subgroup)."""
    for key, value in caps.items():
        where = f"{field_name}.{_path}{key}" if _path else f"{field_name}.{key}"
        if isinstance(value, dict):
            _validate_capability_block(value, field_name=field_name, _path=f"{_path}{key}.")
        elif value not in _CAPABILITY_STATES:
            raise ManifestError(f"{where}: capability state must be one of {list(_CAPABILITY_STATES)} (got {value!r})")


def _coerce_qualifiers(value: Any, *, field_name: str) -> dict[str, dict[str, str]]:
    """Coerce the optional capability_qualifiers block (id/group -> {key: value})."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ManifestError(f"{field_name}: must be a mapping of capability id/group to qualifiers")
    out: dict[str, dict[str, str]] = {}
    for cap_key, quals in value.items():
        if not isinstance(quals, dict):
            raise ManifestError(f"{field_name}.{cap_key}: must be a mapping of qualifier keys to values")
        out[str(cap_key)] = {str(k): str(v) for k, v in quals.items()}
    return out


def _coerce_string_mapping(value: Any, *, field_name: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ManifestError(f"{field_name}: must be a mapping of string values")
    return {str(k): str(v) for k, v in value.items()}


# --- optional second layer: per-instance config (nv-storage two-layer model) --


def _load_instance_config(config: Mapping[str, Any], manifest_path: Path) -> Mapping[str, Any] | None:
    """Load the optional per-instance ``config.yaml`` ``instance:`` section.

    Sourced from the ``instance_config_path`` config key, else auto-discovered as
    a sibling ``config.yaml`` next to the manifest. Returns the ``instance``
    mapping, or ``None`` when no instance config is present. Raises
    ``ManifestError`` on a malformed file.
    """
    explicit = str(config.get("instance_config_path") or "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise ManifestError(f"instance config file not found: {path}")
    else:
        path = manifest_path.parent / "config.yaml"
        if not path.is_file():
            return None

    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ManifestError(f"failed to parse instance config {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ManifestError(f"instance config {path} must be a YAML mapping at the top level")
    return _coerce_mapping(raw.get("instance"), field_name="instance")


def _apply_instance_config(provider: Provider, instance: Mapping[str, Any]) -> Provider:
    """Overlay an instance config's provider overrides onto a manifest ``Provider``.

    Applies ``defaultTenant`` (the tenant cross-check target), ``storageClasses``,
    and ``capabilities`` (id/group -> enabled/disabled) on top of the manifest's
    resolved ``expected_capabilities``.
    """
    inst_provider = _coerce_mapping(instance.get("provider"), field_name="instance.provider")

    default_tenant = inst_provider.get("defaultTenant")
    if default_tenant is not None and not isinstance(default_tenant, str):
        raise ManifestError("instance.provider.defaultTenant: must be a string")

    storage_classes = _coerce_protocols(
        inst_provider.get("storageClasses"), field_name="instance.provider.storageClasses"
    )

    overrides = _parse_instance_capability_overrides(
        _coerce_mapping(inst_provider.get("capabilities"), field_name="instance.provider.capabilities")
    )
    expected = dict(provider.expected_capabilities)
    states = dict(provider.capability_states)
    for cap_id in CAPABILITY_IDS:
        override = _resolve_capability_override(overrides, cap_id)
        if override is not None:
            expected[cap_id] = override
            if override:
                states[cap_id] = states.get(cap_id, "native") if states.get(cap_id) != "none" else "native"
            else:
                states[cap_id] = "none"

    return replace(
        provider,
        tenant_id=default_tenant if default_tenant else provider.tenant_id,
        storage_classes=storage_classes or provider.storage_classes,
        expected_capabilities=expected,
        capability_states=states,
    )


def _parse_instance_capability_overrides(raw: Mapping[str, Any]) -> dict[str, bool]:
    """Map an instance ``capabilities:`` block (id|group -> enabled/disabled).

    Keys are capability ids or dotted group prefixes (e.g. ``"volume.create"``,
    ``"quota"``); values are ``enabled`` / ``disabled`` (or a YAML bool). An
    unknown key or non-bool value is a ``ManifestError`` (catches typos).
    """
    overrides: dict[str, bool] = {}
    for key, value in raw.items():
        key = str(key)
        if key not in _CAPABILITY_OVERRIDE_KEYS:
            raise ManifestError(f"instance.provider.capabilities: unknown capability key {key!r}")
        overrides[key] = _coerce_override_value(key, value)
    return overrides


def _coerce_override_value(key: str, value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        norm = value.strip().lower()
        if norm == "enabled":
            return True
        if norm == "disabled":
            return False
    raise ManifestError(f"instance.provider.capabilities.{key}: must be 'enabled' or 'disabled' (got {value!r})")


def _resolve_capability_override(overrides: Mapping[str, bool], cap_id: str) -> bool | None:
    """Most-specific override for ``cap_id`` (exact id, then group prefixes)."""
    key = cap_id
    while True:
        if key in overrides:
            return overrides[key]
        dot = key.rfind(".")
        if dot < 0:
            return None
        key = key[:dot]


def _capability_override_key_set() -> frozenset[str]:
    """Every accepted override key: each capability id and its group prefixes."""
    keys: set[str] = set()
    for cap_id in CAPABILITY_IDS:
        key = cap_id
        keys.add(key)
        while (dot := key.rfind(".")) >= 0:
            key = key[:dot]
            keys.add(key)
    return frozenset(keys)


_CAPABILITY_OVERRIDE_KEYS = _capability_override_key_set()
