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

"""``StorageProvider`` ABC, value types, and error taxonomy.

Mirrors nv-storage's ``spi/storageprovider`` contract. Defines the abstract
``StorageProvider`` interface for provider-implemented storage shims: every
tenant/volume/quota method takes a request object and returns either the domain
type, a response object, or ``None``.

Providers author a shim with a single model: subclass ``Implementation``,
override only the surfaces the backend serves, and hand it to
``new_implementation()``. The SDK *detects* which surfaces are supported from
the overridden method set, folds in config overrides and the
``capability_qualifiers`` hook, advertises the merged states on
``properties().capabilities()``, and gates the rest.

``properties().capabilities()`` returns the typed, navigable capability tree
(state + L2 qualifiers per surface); consumers read it there rather than
touching the SDK-internal ``_capability_list``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Literal

VolumeType = Literal["block", "file"]
VolumeState = Literal["creating", "available", "failed", "deleting"]

#: Merged "effective" state of one capability on a provider endpoint - the value
#: a caller routes on. Only ``"supported"`` is routable; the others are distinct,
#: actionable diagnostics. ``None`` is unspecified and treated as not-supported
#: (fail safe). Mirrors nv-storage's ``CapabilityState``.
CapabilityState = Literal["supported", "disabled", "unavailable", "unimplemented"]

API_VERSION = "v1alpha1"

#: The ``instance_id`` an impl gets when it declares none - the third
#: registration-key / UDS-path segment for a single-instance provider.
DEFAULT_INSTANCE_ID = "default"


def instance_or_default(instance_id: str) -> str:
    """Resolve an empty ``instance_id`` to ``DEFAULT_INSTANCE_ID``.

    The one place the "" -> "default" rule lives, shared by the SDK base class
    (which echoes the resolved value on ``properties()``) and the transport
    identity layer (registration key, UDS path, identity validation).
    """
    return instance_id or DEFAULT_INSTANCE_ID


@dataclass(frozen=True)
class Tenant:
    """A backend tenant - the shim's view of an isolation boundary on the backend.

    AWS account, VAST tenant, NetApp SVM, Azure subscription, etc. The
    minimum a backend MUST report is ``id``; ``name`` and ``attributes``
    are best-effort metadata.
    """

    id: str
    name: str | None = None
    attributes: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TenantQuota:
    """Tenant-level storage utilization.

    A backend that partitions quota by tier (the ``tiered`` qualifier on
    ``tenant.listQuotas``) reports one ``TenantQuota`` per tier, each with
    ``tier`` set; an untiered backend reports a single entry with ``tier`` None.
    """

    tenant_id: str
    hard_limit_bytes: int
    used_bytes: int
    name: str
    # Tier this quota accounts for (e.g. a Lustre deployment type like
    # "PERSISTENT_2"). None on the aggregate quota from get_tenant_quota and on
    # untiered backends; set on each per-tier entry from list_tenant_quotas.
    tier: str | None = None
    # Backend-stable identifier this quota is looked up by, distinct from
    # tenant_id (a backend-specific quota code). Empty when the backend has no
    # stable per-quota id.
    id: str = ""


@dataclass(frozen=True)
class QuotaLimits:
    """Hard caps for a quota subject.

    Per-dimension: ``None`` = unlimited / unset on that dimension; positive
    int = capped at that value. Backends that do not enforce a dimension
    (per the quota capability's ``QUAL_INODES`` qualifier etc.) silently ignore
    the field; callers pre-check the qualifier if they need to surface a
    diagnostic.
    """

    bytes: int | None = None
    inodes: int | None = None


@dataclass(frozen=True)
class QuotaUsage:
    """Observed usage for a quota subject, as reported by the backend.

    Per-dimension: ``None`` = backend does not report usage on that
    dimension (e.g. inode counters disabled, or the backend has no such
    concept). ``usage`` is ignored on ``set_*`` input; the backend's
    actual values are echoed on return.
    """

    bytes: int | None = None
    inodes: int | None = None


@dataclass(frozen=True)
class VersionMetadata:
    """Descriptive metadata about a party and its offering - human-facing.

    Reused for the StorageProvider implementor
    (``ProviderProperties.provider_metadata``), the storage backend it fronts
    (``ProviderProperties.backend_metadata``), and the gateway itself.

    Machine identity is NOT here: the registration/addressing key is carried as
    first-class ``provider_namespace`` + ``provider_id`` scalars on
    ``ProviderProperties``, so the DNS-label / key constraints apply there, not
    to this bag.

    ``version`` is context-dependent: for an implementor (provider/gateway) it
    MUST be semver (``"1.2.3"``); for a backend it is the backing system's
    version passed through as-is (opaque, e.g. ``"2.15"``) and is not
    constrained.
    """

    vendor_name: str = ""  # org display name, e.g. "NVIDIA", "VAST Data"
    vendor_docs: str = ""  # URL to the vendor's API / product docs (optional)
    name: str = ""  # product / offering display name, e.g. "AWS FSx Lustre"
    version: str = ""  # offering version; implementor -> semver, backend -> opaque passthrough
    description: str = ""  # optional brief, human-facing description


# Qualifier-value type aliases - the documented values of the corresponding
# capability qualifiers (L2). An absent qualifier means the permissive default.
IDAssignment = Literal["caller", "backend"]
QuotaAccounting = Literal["nested", "partitioned"]

# Qualifier keys are the SDK-owned vocabulary for ``Capability.qualifiers`` (L2):
# registry-governed semantic facts a caller may need to behave correctly. A
# provider attaches them via the ``capability_qualifiers()`` hook
# (``Implementation``); keys absent from a capability carry their permissive
# default. Values are the documented strings noted below.
QUAL_ID_ASSIGNMENT = "idAssignment"  # who mints the quota id; value: an IDAssignment ("caller"|"backend")
QUAL_BYTE_GRANULARITY = "byteGranularity"  # min byte alignment as a decimal int; absent = byte-exact
QUAL_MULTI_PATH_BINDING = "multiPathBinding"  # "true": one quota id governs multiple paths (Lustre)
QUAL_ACCOUNTING = "accounting"  # nested-subject accounting; value: a QuotaAccounting ("nested"|"partitioned")
QUAL_INODES = "inodes"  # "true"|"false": backend honors inode (file-count) limits on this surface
QUAL_DEFAULT_USER_SLOT = "defaultUserSlot"  # "true"|"false": user-quota surface supports the fs-wide default-user slot
QUAL_MULTI_TENANT = "multiTenant"  # "true"|"false": backend manages multiple tenants (vs. a single fixed tenant)
QUAL_TIERED = "tiered"  # "true"|"false": backend partitions tenant quota by tier (list_tenant_quotas returns one per tier; get_tenant_quota honors req.tier)

# Capability group prefixes - the dotted ancestors of the leaf ids below. They
# are valid qualifier keys: a group key fans out to every leaf beneath it.
CAP_GROUP_TENANT = "tenant"
CAP_GROUP_VOLUME = "volume"
CAP_GROUP_QUOTA = "quota"
CAP_GROUP_DIRECTORY_QUOTA = f"{CAP_GROUP_QUOTA}.directory"
CAP_GROUP_USER_QUOTA = f"{CAP_GROUP_QUOTA}.user"

# Capability registry ids - the SDK-owned identifiers carried as ``Capability.id``
# and the keys a capability claim (manifest) or qualifier may target (by id, or a
# dotted group prefix of one).
CAP_TENANT_LIST = f"{CAP_GROUP_TENANT}.list"
CAP_TENANT_GET = f"{CAP_GROUP_TENANT}.get"
CAP_TENANT_GET_QUOTA = f"{CAP_GROUP_TENANT}.getQuota"
CAP_TENANT_LIST_QUOTAS = f"{CAP_GROUP_TENANT}.listQuotas"
CAP_VOLUME_LIST = f"{CAP_GROUP_VOLUME}.list"
CAP_VOLUME_GET = f"{CAP_GROUP_VOLUME}.get"
CAP_VOLUME_CREATE = f"{CAP_GROUP_VOLUME}.create"
CAP_VOLUME_DELETE = f"{CAP_GROUP_VOLUME}.delete"
CAP_DIRECTORY_QUOTA_LIST = f"{CAP_GROUP_DIRECTORY_QUOTA}.list"
CAP_DIRECTORY_QUOTA_GET = f"{CAP_GROUP_DIRECTORY_QUOTA}.get"
CAP_DIRECTORY_QUOTA_SET = f"{CAP_GROUP_DIRECTORY_QUOTA}.set"
CAP_DIRECTORY_QUOTA_DELETE = f"{CAP_GROUP_DIRECTORY_QUOTA}.delete"
CAP_USER_QUOTA_LIST = f"{CAP_GROUP_USER_QUOTA}.list"
CAP_USER_QUOTA_GET = f"{CAP_GROUP_USER_QUOTA}.get"
CAP_USER_QUOTA_SET = f"{CAP_GROUP_USER_QUOTA}.set"
CAP_USER_QUOTA_DELETE = f"{CAP_GROUP_USER_QUOTA}.delete"

#: The complete set of capability ids the SDK knows about - the registry the
#: manifest declares against and the validation suite probes.
CAPABILITY_IDS: tuple[str, ...] = (
    CAP_TENANT_LIST,
    CAP_TENANT_GET,
    CAP_TENANT_GET_QUOTA,
    CAP_TENANT_LIST_QUOTAS,
    CAP_VOLUME_LIST,
    CAP_VOLUME_GET,
    CAP_VOLUME_CREATE,
    CAP_VOLUME_DELETE,
    CAP_DIRECTORY_QUOTA_LIST,
    CAP_DIRECTORY_QUOTA_GET,
    CAP_DIRECTORY_QUOTA_SET,
    CAP_DIRECTORY_QUOTA_DELETE,
    CAP_USER_QUOTA_LIST,
    CAP_USER_QUOTA_GET,
    CAP_USER_QUOTA_SET,
    CAP_USER_QUOTA_DELETE,
)


@dataclass(frozen=True)
class Capability:
    """One API surface's merged effective state and L2 qualifiers on this endpoint.

    ``id`` is a value from the SDK-owned capability registry (e.g.
    ``"quota.user.set"``). ``state`` is the merged effective ``CapabilityState``
    a caller routes on; ``qualifiers`` are registry-governed semantic facts (L2).
    Purely advisory attributes live on ``ProviderProperties.attributes`` (L3),
    never here.
    """

    id: str
    state: CapabilityState | None = None
    qualifiers: Mapping[str, str] = field(default_factory=dict)


def _resolve_qualifiers(qmap: Mapping[str, Mapping[str, str]], cap_id: str) -> dict[str, str]:
    """Qualifiers for ``cap_id``, merging group prefixes then the leaf's own entry.

    Least-specific first so the leaf wins on conflicting keys: ``"quota"`` then
    ``"quota.user"`` then ``"quota.user.set"``. A pure read convenience that lets
    a provider declare a fact once for a whole group.
    """
    keys = [cap_id]
    key = cap_id
    while (dot := key.rfind(".")) >= 0:
        key = key[:dot]
        keys.append(key)
    merged: dict[str, str] = {}
    for key in reversed(keys):
        merged.update(qmap.get(key, {}))
    return merged


@dataclass(frozen=True)
class ProviderProperties:
    """Static declaration of a provider's identity, capabilities, and semantics.

    Returned by ``StorageProvider.properties()`` and immutable for the lifetime
    of a shim instance. Callers branch on ``capabilities()`` rather than catching
    ``NotSupportedError`` after the fact; validation suites assert advertised
    behavior against the running shim.

    ``provider_namespace`` + ``provider_id`` are required; ``instance_id`` is
    OPTIONAL and defaults to ``"default"``. ``backend_metadata`` is OPTIONAL
    (``None`` = undeclared).

    ``capabilities()`` is the single model for inspecting optional API surfaces:
    navigate the typed tree and read merged ``CapabilityState`` and L2 qualifiers.
    The flat ``_capability_list`` behind it is SDK-internal wire input, set only
    by trusted builders (``new_implementation()``); consumers use ``capabilities()``.
    """

    provider_namespace: str
    provider_id: str
    provider_metadata: VersionMetadata
    sdk_version: str
    storage_type: Literal["file", "block"]
    storage_protocols: list[str]

    instance_id: str = ""
    backend_metadata: VersionMetadata | None = None
    kubernetes_storage_classes: list[str] = field(default_factory=list)

    # SDK-internal construction/wire input: merged effective state per surface.
    # Set only by ``new_implementation()``; consumers read via ``capabilities()``.
    _capability_list: list[Capability] = field(default_factory=list)

    attributes: dict[str, str] = field(default_factory=dict)

    def capabilities(self) -> Capabilities:
        """The advertised capabilities as a typed, navigable tree.

        The single capability accessor: walk to a group or a leaf and read its
        ``state`` / ``is_supported`` or its typed qualifiers, instead of
        string-keying a flat list. Rebuilt from the advertised list each call
        (retain the result if you read it repeatedly). The returned tree also
        exposes ``effective_list()`` / ``raw_list()`` flat views.
        """
        return _new_capabilities(self._capability_list)


@dataclass(frozen=True)
class DirectoryQuota:
    """Per-directory-tree quota record on a volume.

    Identity keys vary by backend (see the directory-quota capability's
    ``QUAL_ID_ASSIGNMENT`` qualifier): ``path`` is the primary key on
    ``"backend"`` backends (VAST), ``id`` is the primary key on ``"caller"``
    backends (Lustre, where the caller mints the project id). Returned DTOs MUST
    populate ``id`` regardless of assignment mode.
    """

    tenant_id: str
    volume_id: str
    path: str | None = None  # volume-relative; REQUIRED when id_assignment="backend"; OPTIONAL on "caller"
    id: str | None = None  # backend-native id; REQUIRED input on "caller"; MUST be populated on return
    hard: QuotaLimits | None = None  # None = managed entity with no caps declared on any dimension
    usage: QuotaUsage = field(default_factory=QuotaUsage)
    attributes: Mapping[str, str] = field(
        default_factory=dict
    )  # provider-defined opaque metadata; round-trip as received


@dataclass(frozen=True)
class UserQuota:
    """Per-user quota record on a volume.

    ``user=None`` addresses the volume's default-user slot (one per volume,
    gated by the user-quota capability's ``QUAL_DEFAULT_USER_SLOT`` qualifier). A
    non-None ``user`` identifies an override; the backend infers the
    identifier kind from format (numeric -> uid, non-numeric -> username).
    """

    tenant_id: str
    volume_id: str
    user: str | None  # None = default-user slot (singleton per volume); str = per-user override
    hard: QuotaLimits | None = None  # None = managed entity with no caps declared on any dimension
    usage: QuotaUsage = field(default_factory=QuotaUsage)
    attributes: Mapping[str, str] = field(
        default_factory=dict
    )  # provider-defined opaque metadata; round-trip as received


@dataclass(frozen=True)
class MountSpec:
    """Linux ``mount(8)``-shaped access info for bare-metal / VM consumers.

    Fields map directly to ``mount -t <fs_type> -o <options> <source>
    <target>`` so a caller composes the command (or an ``/etc/fstab``
    line) without any vendor-specific logic.
    """

    fs_type: str
    source: str
    options: str | None = None


@dataclass(frozen=True)
class CsiSpec:
    """``spec.csi`` payload for a statically-provisioned PV.

    Fields map 1:1 to ``CSIPersistentVolumeSource``; the operator can
    build a PV manifest from this without consulting the CSI driver.
    """

    driver: str
    volume_handle: str
    fs_type: str | None = None
    volume_attributes: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Volume:
    """A provisioned volume in a backend tenant.

    The only universally-meaningful identifier is ``id``. ``mount`` /
    ``csi`` carry access info shapes most backends report; everything
    vendor-specific lands in ``attributes``. Usage metrics are optional
    (``None`` means "not reported").
    """

    tenant_id: str
    id: str
    size_bytes: int
    created_at: datetime
    type: VolumeType
    state: VolumeState

    name: str | None = None
    mount: MountSpec | None = None
    csi: CsiSpec | None = None
    tier: str | None = None
    tags: Mapping[str, str] = field(default_factory=dict)
    attributes: Mapping[str, str] = field(default_factory=dict)

    used_bytes: int | None = None
    available_bytes: int | None = None
    used_inodes: int | None = None
    available_inodes: int | None = None


@dataclass(frozen=True)
class TagFilter:
    """Predicate over volume tags, used by ``list_volumes``.

    Matches a volume when ``tag[key]`` exists and (if ``values`` is
    non-empty) its value is one of ``values``. ``values=()`` is an
    existence check on ``key``. Multiple ``TagFilter``s in one call are
    AND'd together.
    """

    key: str
    values: tuple[str, ...] = ()


# ===== request / response objects =====
#
# Every tenant/volume/quota method takes a XxxRequest and, mirroring the wire,
# returns either the domain type (single-entity getters), a XxxResponse (list
# calls, so they can grow pagination later), or None (deletes). A request object
# keeps optional fields self-documenting at the call site and lets the contract
# gain fields without churning signatures. ``tenant_id=None`` selects the
# configured default tenant (resolved by the SDK base class, not per-impl).


@dataclass(frozen=True)
class ListTenantsRequest:
    """Arguments to ``StorageProvider.list_tenants``."""

    ids: tuple[str, ...] = ()  # restrict to matching ids; unknown ids silently omitted


@dataclass(frozen=True)
class ListTenantsResponse:
    """Result of ``StorageProvider.list_tenants``."""

    tenants: tuple[Tenant, ...] = ()


@dataclass(frozen=True)
class GetTenantRequest:
    """Arguments to ``StorageProvider.get_tenant``."""

    tenant_id: str | None = None  # None = default tenant


@dataclass(frozen=True)
class GetTenantQuotaRequest:
    """Arguments to ``StorageProvider.get_tenant_quota``."""

    tenant_id: str | None = None  # None = default tenant
    # Optional tier filter. None = the aggregate across all tiers; set = that
    # tier's quota. Backends that do not partition quota by tier ignore it and
    # return the aggregate; use list_tenant_quotas to enumerate every tier.
    tier: str | None = None
    # Optional backend lookup key (TenantQuota.id). None = address by tier /
    # aggregate. When set it takes precedence over tier (NOT_FOUND if the id is
    # unknown); backends with no stable per-quota id ignore it.
    id: str | None = None


@dataclass(frozen=True)
class ListTenantQuotasRequest:
    """Arguments to ``StorageProvider.list_tenant_quotas``."""

    tenant_id: str | None = None  # None = default tenant


@dataclass(frozen=True)
class ListTenantQuotasResponse:
    """Result of ``StorageProvider.list_tenant_quotas`` - one ``TenantQuota`` per tier
    on a tiered backend, or a single untiered entry."""

    tenant_quotas: tuple[TenantQuota, ...] = ()


@dataclass(frozen=True)
class CreateVolumeRequest:
    """Arguments to ``StorageProvider.create_volume``."""

    size_bytes: int
    volume_type: VolumeType
    tenant_id: str | None = None  # None = default tenant
    name: str | None = None
    tier: str | None = None
    tags: Mapping[str, str] | None = None


@dataclass(frozen=True)
class DeleteVolumeRequest:
    """Arguments to ``StorageProvider.delete_volume``."""

    volume_id: str
    tenant_id: str | None = None  # None = default tenant


@dataclass(frozen=True)
class ListVolumesRequest:
    """Arguments to ``StorageProvider.list_volumes``."""

    tenant_id: str | None = None  # None = default tenant
    ids: tuple[str, ...] = ()
    tag_filters: tuple[TagFilter, ...] = ()


@dataclass(frozen=True)
class ListVolumesResponse:
    """Result of ``StorageProvider.list_volumes``."""

    volumes: tuple[Volume, ...] = ()


@dataclass(frozen=True)
class GetVolumeRequest:
    """Arguments to ``StorageProvider.get_volume``."""

    volume_id: str
    tenant_id: str | None = None  # None = default tenant


@dataclass(frozen=True)
class ListDirectoryQuotasRequest:
    """Arguments to ``StorageProvider.list_directory_quotas``."""

    volume_id: str
    tenant_id: str | None = None  # None = default tenant


@dataclass(frozen=True)
class ListDirectoryQuotasResponse:
    """Result of ``StorageProvider.list_directory_quotas``."""

    directory_quotas: tuple[DirectoryQuota, ...] = ()


@dataclass(frozen=True)
class GetDirectoryQuotaRequest:
    """Arguments to ``StorageProvider.get_directory_quota`` (at least one of path/id)."""

    volume_id: str
    tenant_id: str | None = None  # None = default tenant
    path: str | None = None
    id: str | None = None


@dataclass(frozen=True)
class SetDirectoryQuotaRequest:
    """Arguments to ``StorageProvider.set_directory_quota``."""

    quota: DirectoryQuota


@dataclass(frozen=True)
class DeleteDirectoryQuotaRequest:
    """Arguments to ``StorageProvider.delete_directory_quota`` (at least one of path/id)."""

    volume_id: str
    tenant_id: str | None = None  # None = default tenant
    path: str | None = None
    id: str | None = None


@dataclass(frozen=True)
class ListUserQuotasRequest:
    """Arguments to ``StorageProvider.list_user_quotas``."""

    volume_id: str
    tenant_id: str | None = None  # None = default tenant


@dataclass(frozen=True)
class ListUserQuotasResponse:
    """Result of ``StorageProvider.list_user_quotas``."""

    user_quotas: tuple[UserQuota, ...] = ()


@dataclass(frozen=True)
class GetUserQuotaRequest:
    """Arguments to ``StorageProvider.get_user_quota``."""

    volume_id: str
    tenant_id: str | None = None  # None = default tenant
    user: str | None = None  # None = default-user slot


@dataclass(frozen=True)
class SetUserQuotaRequest:
    """Arguments to ``StorageProvider.set_user_quota``."""

    quota: UserQuota


@dataclass(frozen=True)
class DeleteUserQuotaRequest:
    """Arguments to ``StorageProvider.delete_user_quota``."""

    volume_id: str
    tenant_id: str | None = None  # None = default tenant
    user: str | None = None  # None = default-user slot


class StorageApiError(Exception):
    """Base for all shim errors."""


class AuthenticationError(StorageApiError):
    """Backend unreachable or credentials rejected."""


class NotFoundError(StorageApiError):
    """Lookup of an unknown volume / tenant."""


class NotSupportedError(StorageApiError):
    """Optional shim surface not offered by this backend.

    Raised by the default ``create_volume`` / ``delete_volume`` on
    managed-K8s providers whose CSI driver owns lifecycle, and by backends
    that don't expose an optional argument value (e.g. a tier they don't
    support).
    """


class QuotaExceededError(StorageApiError):
    """``create_volume`` that would breach the tenant quota."""


class ValidationError(StorageApiError):
    """Shim-side input check failed before the call reached the backend.

    Raised on e.g. ``DirectoryQuota.id`` being ``None`` when the directory-quota
    capability advertises ``QUAL_ID_ASSIGNMENT == "caller"``, neither
    ``path`` nor ``id`` supplied to ``get_directory_quota`` /
    ``delete_directory_quota``, or malformed ``DirectoryQuota.path``.
    """


class ConflictError(StorageApiError):
    """Backend write conflict or cross-key disagreement.

    Raised when the backend reports a write conflict (concurrent
    mutation), or when ``get_*`` / ``delete_*`` was called with both
    ``path`` and ``id`` and the natural-key lookup returned a record
    whose secondary key disagreed with the caller's input. Callers
    SHOULD re-fetch via ``get_*`` and retry with fresh state; the shim
    does NOT serialize concurrent writes.
    """


class UnavailableError(StorageApiError):
    """A surface that is serviceable in principle but not from this endpoint
    right now - a **transient** failure the caller SHOULD retry or route around.

    Distinct from ``NotSupportedError`` (a permanent refusal). Maps to gRPC
    ``UNAVAILABLE`` / HTTP 503.
    """


class StorageProvider(ABC):
    """Provider-implemented contract for one or more backend storage tenants.

    Implementations MUST be safe to call concurrently from multiple
    threads (the future REST/gRPC server may dispatch in parallel). The
    implementation is constructed once at process start via the
    module-level ``build_api()`` factory; per-call credentials / auth
    handling is internal to the implementation.

    A shim implements the optional surfaces it backs. Surfaces it does not back
    fall back to the base method (which raises ``NotSupportedError``), or the
    shim MAY override them with an explicit stub that raises
    ``NotSupportedError`` / ``NotImplementedError`` (e.g. to give a custom
    message). Which surfaces are *supported* is declared in the provider manifest
    (the contract); the validation suite verifies each declared-supported surface
    by probing it at runtime, so a stub under a ``supported`` claim fails the
    suite.

    Every tenant-scoped method takes a request object whose ``tenant_id`` is
    ``None`` by default. ``None`` selects the shim's configured default tenant
    (typically read from an env var or ConfigMap at construction time, then
    resolved by the impl - see the reference shims' ``_resolve_tenant`` helper).
    Single-tenant providers configure the default and never set it on the request;
    multi-tenant providers either configure no default and set ``tenant_id``
    explicitly on every call, or set a default and override per call.

    ``health_check`` is intentionally NOT tenant-scoped - it answers "can
    the shim reach the backend at all". Per-tenant authorization
    surfaces on the actual tenant-scoped calls.
    """

    @abstractmethod
    def properties(self) -> ProviderProperties:
        """Return this shim's identity, capability, and semantics declaration.

        Required on every shim - no default. MUST return the same
        ``ProviderProperties`` value on every call for a given shim
        lifetime; capabilities are properties of the wrapped backend's
        design and version, not its runtime state.

        Callers branch on the advertised ``capabilities`` rather than catching
        ``NotSupportedError`` after the fact; validation suites assert
        advertised behavior against the running shim.
        """

    @abstractmethod
    def health_check(self) -> None:
        """Authenticated round-trip to the backend.

        * Backend unreachable or credentials rejected -> raises ``AuthenticationError``.
        * Returns ``None`` on success.
        """

    def list_tenants(self, req: ListTenantsRequest) -> ListTenantsResponse:
        """Return every backend tenant the shim has access to (optional).

        ``req.ids`` restricts the result to matching tenant IDs; unknown IDs
        are silently omitted (not an error).

        Implement to back ``tenant.list`` (and declare it ``native`` in the manifest).

        * Not implemented by this backend -> raises ``NotSupportedError``.
        """
        raise NotSupportedError("list_tenants not implemented by this backend")

    def get_tenant(self, req: GetTenantRequest) -> Tenant:
        """Return one tenant by ID, or the configured default when ``req.tenant_id`` is None.

        Default delegates to ``list_tenants`` (so ``tenant.get`` is available
        whenever ``tenant.list`` is); backends with a native single-tenant
        endpoint should override. When ``req.tenant_id`` is None the default impl
        returns the sole tenant if the backend exposes exactly one, otherwise it
        raises ``ValidationError`` (ambiguous) - a multi-tenant backend MUST
        override to resolve its configured default.

        * ``req.tenant_id`` not found -> raises ``NotFoundError``.
        * ``req.tenant_id`` None and the backend exposes >1 tenant -> raises ``ValidationError``.
        * Backend does not support tenant enumeration -> raises ``NotSupportedError``.
        """
        tenants = self.list_tenants(
            ListTenantsRequest(ids=(req.tenant_id,) if req.tenant_id is not None else ())
        ).tenants
        if req.tenant_id is None:
            if len(tenants) == 1:
                return tenants[0]
            raise ValidationError(
                "get_tenant requires an explicit tenant_id when the backend exposes "
                f"{len(tenants)} tenants; override get_tenant to resolve the configured default"
            )
        for t in tenants:
            if t.id == req.tenant_id:
                return t
        raise NotFoundError(f"tenant {req.tenant_id!r} not found")

    @abstractmethod
    def get_tenant_quota(self, req: GetTenantQuotaRequest) -> TenantQuota:
        """Return overall storage utilization for the named (or default) tenant.

        Backends that partition quota by tier honor ``req.tier`` / ``req.id``;
        untiered backends ignore them and return the aggregate.

        * ``req.tenant_id`` not found -> raises ``NotFoundError``.
        """

    def list_tenant_quotas(self, req: ListTenantQuotasRequest) -> ListTenantQuotasResponse:
        """Enumerate the named (or default) tenant's quotas (optional).

        Backends that partition quota by tier (advertised by the ``tiered``
        qualifier on ``tenant.listQuotas``) return one ``TenantQuota`` per tier,
        each with ``tier`` set; an untiered backend returns a single entry with
        ``tier`` None (equivalent to ``get_tenant_quota``). Callers fall back to
        ``get_tenant_quota`` when this is unimplemented.

        Implement to back ``tenant.listQuotas`` (and declare it ``native`` in the manifest).

        * ``req.tenant_id`` not found -> raises ``NotFoundError``.
        * Not implemented by this backend -> raises ``NotSupportedError``.
        """
        raise NotSupportedError("list_tenant_quotas not implemented by this backend")

    def create_volume(self, req: CreateVolumeRequest) -> Volume:
        """Provision a new volume in the named (or default) tenant (optional).

        Providers whose managed-K8s CSI driver handles dynamic provisioning leave this
        unimplemented (inherit this base raise, or override with a stub that
        raises) and declare ``volume.create: none`` in the manifest.

        The returned ``Volume`` MUST have ``id`` populated even when the
        backend provisions asynchronously - callers poll ``get_volume``
        until ``state == "available"``.

        * ``req.tenant_id`` not found -> raises ``NotFoundError``.
        * Requested size would breach the tenant quota -> raises ``QuotaExceededError``.
        * ``req.tier`` not supported by this backend -> raises ``NotSupportedError``.
        * Not implemented by this backend -> raises ``NotSupportedError``.
        """
        raise NotSupportedError("create_volume not implemented by this backend")

    def delete_volume(self, req: DeleteVolumeRequest) -> None:
        """Tear down a volume previously returned by ``create_volume`` (optional).

        Implementations that support ``create_volume`` MUST also support
        ``delete_volume`` so callers can release resources they provisioned.

        * ``req.tenant_id`` not found -> raises ``NotFoundError``.
        * ``req.volume_id`` already gone -> no-op, no error.
        * Not implemented by this backend -> raises ``NotSupportedError``.
        """
        raise NotSupportedError("delete_volume not implemented by this backend")

    @abstractmethod
    def list_volumes(self, req: ListVolumesRequest) -> ListVolumesResponse:
        """Return volumes in the named (or default) tenant, optionally filtered.

        ``req.ids`` restricts the result to matching volume IDs; unknown IDs
        are silently omitted (not an error). ``req.tag_filters`` is a
        conjunction - every filter MUST match. A single call NEVER
        spans tenants; backends MUST always scope to the selected tenant
        regardless of filters.

        * ``req.tenant_id`` not found -> raises ``NotFoundError``.
        """

    def get_volume(self, req: GetVolumeRequest) -> Volume:
        """Return the volume with ``req.volume_id`` from the named (or default) tenant.

        Default delegates to ``list_volumes`` (so ``volume.get`` is always
        available); backends with a native single-volume endpoint should
        override.

        * ``req.tenant_id`` not found -> raises ``NotFoundError``.
        * ``req.volume_id`` not found -> raises ``NotFoundError``.
        """
        resp = self.list_volumes(ListVolumesRequest(tenant_id=req.tenant_id, ids=(req.volume_id,)))
        for vol in resp.volumes:
            if vol.id == req.volume_id:
                return vol
        raise NotFoundError(f"volume {req.volume_id!r} not found")

    # ===== Directory quotas =====

    def list_directory_quotas(self, req: ListDirectoryQuotasRequest) -> ListDirectoryQuotasResponse:
        """Enumerate every directory-tree quota on ``req.volume_id``.

        Each returned ``DirectoryQuota`` has ``id`` populated regardless
        of the directory-quota capability's ``QUAL_ID_ASSIGNMENT`` qualifier.

        Implement to back ``quota.directory.list`` (and declare it ``native`` in
        the manifest). Backends that can set quotas but cannot enumerate them
        (Lustre) leave this unimplemented and override ``get_directory_quota``
        natively instead.

        * Listing not supported (e.g. Lustre) -> raises ``NotSupportedError``.
        * ``req.tenant_id`` / ``req.volume_id`` not found -> raises ``NotFoundError``.
        """
        raise NotSupportedError("list_directory_quotas not implemented by this backend")

    def get_directory_quota(self, req: GetDirectoryQuotaRequest) -> DirectoryQuota:
        """Lookup a directory-tree quota by ``path``, ``id``, or both.

        At least one of ``req.path`` / ``req.id`` MUST be supplied. When both
        are supplied, the lookup verifies they identify the same record.

        Default delegates to ``list_directory_quotas`` (so ``quota.directory.get``
        is available whenever ``quota.directory.list`` is); backends with a
        native single-record endpoint (or no list surface) should override.

        * Neither ``path`` nor ``id`` supplied -> raises ``ValidationError``.
        * Surface not supported -> raises ``NotSupportedError``.
        * No record matches -> raises ``NotFoundError``.
        * Both keys supplied and disagree -> raises ``ConflictError``.
        """
        if req.path is None and req.id is None:
            raise ValidationError("get_directory_quota requires at least one of `path` or `id`")
        resp = self.list_directory_quotas(ListDirectoryQuotasRequest(tenant_id=req.tenant_id, volume_id=req.volume_id))
        match = _match_directory_quota(resp.directory_quotas, path=req.path, id=req.id)
        if match.full is not None:
            return match.full
        if match.partial is not None:
            p = match.partial
            raise ConflictError(
                f"directory quota lookup mismatch: requested path={req.path!r}, "
                f"id={req.id!r}; found path={p.path!r}, id={p.id!r}"
            )
        raise NotFoundError(
            f"directory quota not found (volume_id={req.volume_id!r}, path={req.path!r}, id={req.id!r})"
        )

    def set_directory_quota(self, req: SetDirectoryQuotaRequest) -> DirectoryQuota:
        """Upsert a directory-tree quota (``req.quota``).

        ``quota.hard=None`` means "managed entity with no caps declared";
        removal goes through ``delete_directory_quota``. Backends silently
        ignore unsupported dimensions on ``quota.hard`` (callers pre-check the
        directory-quota capability's ``QUAL_INODES`` qualifier etc.).

        The returned DTO MUST have ``id`` populated and SHOULD reflect the
        actual stored value. ``quota.usage`` on input is ignored.

        Implement to back ``quota.directory.set`` (and declare it ``native`` in the manifest).

        * Surface not supported -> raises ``NotSupportedError``.
        * ``id_assignment="caller"`` and ``quota.id`` is None -> raises ``ValidationError``.
        * Backend reports a write conflict -> raises ``ConflictError``.
        * ``quota.tenant_id`` / ``quota.volume_id`` not found -> raises ``NotFoundError``.
        """
        raise NotSupportedError("set_directory_quota not implemented by this backend")

    def delete_directory_quota(self, req: DeleteDirectoryQuotaRequest) -> None:
        """Remove a directory-tree quota record.

        Key resolution mirrors ``get_directory_quota``: at least one of
        ``req.path`` / ``req.id`` is required; cross-checks raise
        ``ConflictError`` when both are supplied and disagree. On backends
        advertising ``QUAL_MULTI_PATH_BINDING == "true"`` (Lustre), removing by
        ``id`` removes the record for ALL paths sharing that id.

        Implement to back ``quota.directory.delete`` (and declare it ``native`` in the manifest).

        * Neither ``path`` nor ``id`` supplied -> raises ``ValidationError``.
        * Surface not supported -> raises ``NotSupportedError``.
        * Record already absent -> no-op, no error.
        * Both keys supplied and disagree -> raises ``ConflictError``.
        """
        raise NotSupportedError("delete_directory_quota not implemented by this backend")

    # ===== User quotas =====

    def list_user_quotas(self, req: ListUserQuotasRequest) -> ListUserQuotasResponse:
        """Enumerate every user quota on ``req.volume_id``.

        The default-user slot (``user=None``) is included when set, gated by the
        user-quota capability's ``QUAL_DEFAULT_USER_SLOT`` qualifier.

        Implement to back ``quota.user.list`` (and declare it ``native`` in the
        manifest). Backends that can set user quotas but cannot enumerate them
        (Lustre) leave this unimplemented and override ``get_user_quota``
        natively instead.

        * Listing not supported (e.g. Lustre) -> raises ``NotSupportedError``.
        * ``req.tenant_id`` / ``req.volume_id`` not found -> raises ``NotFoundError``.
        """
        raise NotSupportedError("list_user_quotas not implemented by this backend")

    def get_user_quota(self, req: GetUserQuotaRequest) -> UserQuota:
        """Lookup the quota for ``req.user``.

        ``req.user=None`` addresses the volume's default-user slot. A non-None
        ``user`` matches the backend's stored identifier verbatim.

        Default delegates to ``list_user_quotas`` (so ``quota.user.get`` is
        available whenever ``quota.user.list`` is); backends with a native
        single-record endpoint (or no list surface) should override.

        * Surface not supported -> raises ``NotSupportedError``.
        * No record matches -> raises ``NotFoundError``.
        """
        resp = self.list_user_quotas(ListUserQuotasRequest(tenant_id=req.tenant_id, volume_id=req.volume_id))
        for q in resp.user_quotas:
            if q.user == req.user:
                return q
        raise NotFoundError(f"user quota not found (volume_id={req.volume_id!r}, user={req.user!r})")

    def set_user_quota(self, req: SetUserQuotaRequest) -> UserQuota:
        """Upsert a per-user quota (``req.quota``).

        ``quota.user=None`` targets the default-user slot. ``quota.hard=None``
        means "managed entity with no caps declared"; removal goes through
        ``delete_user_quota``. Unsupported dimensions on ``quota.hard`` are
        silently ignored. ``quota.usage`` on input is ignored.

        Implement to back ``quota.user.set`` (and declare it ``native`` in the manifest).

        * Surface not supported -> raises ``NotSupportedError``.
        * ``quota.user=None`` and ``QUAL_DEFAULT_USER_SLOT`` not advertised
          -> raises ``NotSupportedError``.
        * Backend reports a write conflict -> raises ``ConflictError``.
        """
        raise NotSupportedError("set_user_quota not implemented by this backend")

    def delete_user_quota(self, req: DeleteUserQuotaRequest) -> None:
        """Remove a user quota record.

        ``req.user=None`` removes the default-user slot.

        Implement to back ``quota.user.delete`` (and declare it ``native`` in the manifest).

        * Surface not supported -> raises ``NotSupportedError``.
        * Record already absent -> no-op, no error.
        """
        raise NotSupportedError("delete_user_quota not implemented by this backend")


@dataclass(frozen=True)
class _DirectoryQuotaMatch:
    full: DirectoryQuota | None = None
    partial: DirectoryQuota | None = None


def _match_directory_quota(
    quotas: tuple[DirectoryQuota, ...],
    *,
    path: str | None,
    id: str | None,  # noqa: A002
) -> _DirectoryQuotaMatch:
    """Scan all quotas for a full (both keys agree) and/or partial (one key
    matches while the other disagrees) match.

    Order-independent: a full match always wins over a partial mismatch
    regardless of where each sits in the list (the singular-lookup helper shared
    by the default ``get_`` / ``delete_`` directory-quota impls).
    """
    full: DirectoryQuota | None = None
    partial: DirectoryQuota | None = None
    for q in quotas:
        path_match = path is None or q.path == path
        id_match = id is None or q.id == id
        if path_match and id_match:
            full = q
            break
        if path is not None and id is not None and (q.path == path or q.id == id):
            partial = q
    return _DirectoryQuotaMatch(full=full, partial=partial)


# ===========================================================================
# Implementation authoring model (mirrors nv-storage's new_implementation())
# ===========================================================================
#
# An author subclasses ``Implementation`` (overriding only the surfaces the
# backend actually serves) and hands it to ``new_implementation()``. The SDK then
# *detects* which surfaces are served from the overridden method set, folds in
# any config-driven enable/disable overrides and the ``capability_qualifiers``
# hook's per-node qualifiers / runtime states, and composes a served
# ``StorageProvider`` that advertises the resolved capabilities on ``properties()``
# and *gates* every surface (a non-``supported`` surface raises rather than
# reaching the impl).
#
# The bottom-of-module import breaks the api<->capabilities cycle: the capability
# constants + ``Capability`` this module owns are defined above, so importing the
# typed tree / composition helpers here is safe.
from isvtest.core.storage_provider.capabilities import (  # noqa: E402
    Capabilities,
    ImplementationCapabilities,
    _compose_capabilities,
    _narrow_states,
    _new_capabilities,
)

#: cap_id -> the impl method(s) whose presence backs it. A surface is *detected*
#: as served when the impl overrides ANY listed method (the composite ``get_*``
#: surfaces ride on their ``list_*`` sibling, matching the base delegation).
_CAPABILITY_METHODS: dict[str, tuple[str, ...]] = {
    CAP_TENANT_LIST: ("list_tenants",),
    CAP_TENANT_GET: ("get_tenant", "list_tenants"),
    CAP_TENANT_GET_QUOTA: ("get_tenant_quota",),
    CAP_TENANT_LIST_QUOTAS: ("list_tenant_quotas",),
    CAP_VOLUME_LIST: ("list_volumes",),
    CAP_VOLUME_GET: ("get_volume", "list_volumes"),
    CAP_VOLUME_CREATE: ("create_volume",),
    CAP_VOLUME_DELETE: ("delete_volume",),
    CAP_DIRECTORY_QUOTA_LIST: ("list_directory_quotas",),
    CAP_DIRECTORY_QUOTA_GET: ("get_directory_quota", "list_directory_quotas"),
    CAP_DIRECTORY_QUOTA_SET: ("set_directory_quota",),
    CAP_DIRECTORY_QUOTA_DELETE: ("delete_directory_quota",),
    CAP_USER_QUOTA_LIST: ("list_user_quotas",),
    CAP_USER_QUOTA_GET: ("get_user_quota", "list_user_quotas"),
    CAP_USER_QUOTA_SET: ("set_user_quota",),
    CAP_USER_QUOTA_DELETE: ("delete_user_quota",),
}


class Implementation(StorageProvider):
    """Author-facing base: override only the surfaces the backend serves.

    An ``Implementation`` does NOT build its own ``properties()`` -
    ``new_implementation()`` composes that (identity from the core, capabilities
    from detection + config + the qualifier hook). Overriding ``properties()``
    here is a programming error and raises.

    ``health_check`` is the one required override (a shim must be able to answer
    "can I reach the backend"). Every data-plane surface has a raising default;
    override the ones the backend backs. The optional refinement hooks:

    * ``capability_qualifiers(caps)`` - amend the typed ``ImplementationCapabilities``
      view in place (per-surface L2 qualifiers, and runtime-availability
      narrowing via ``set_state``). Default: no-op.
    * ``backend_metadata()`` - the fronted system's metadata (default: ``None``).
    """

    def properties(self) -> ProviderProperties:  # pragma: no cover - guard
        raise NotImplementedError(
            "Implementation.properties() is composed by new_implementation(); do not call or override it"
        )

    def get_tenant_quota(self, req: GetTenantQuotaRequest) -> TenantQuota:
        raise NotSupportedError("get_tenant_quota not implemented by this backend")

    def list_volumes(self, req: ListVolumesRequest) -> ListVolumesResponse:
        raise NotSupportedError("list_volumes not implemented by this backend")

    def capability_qualifiers(self, caps: ImplementationCapabilities) -> None:
        """Refine the composed capabilities in place (optional; default no-op)."""

    def backend_metadata(self) -> VersionMetadata | None:
        """Fronted system's metadata (default: undeclared)."""
        return None


def _implements(impl: StorageProvider, method: str) -> bool:
    """Whether ``impl`` overrides ``method`` vs. the ``Implementation`` default."""
    return getattr(type(impl), method, None) is not getattr(Implementation, method, None)


def _detect_capabilities(impl: StorageProvider) -> list[Capability]:
    """The declared capability list detected from ``impl``'s overridden methods.

    Each registry surface is ``"supported"`` when the impl backs any of its
    methods, else ``"unimplemented"``. Qualifiers are empty here - the qualifier
    hook and config overrides layer on in ``new_implementation()``.
    """
    caps: list[Capability] = []
    for cap_id in CAPABILITY_IDS:
        served = any(_implements(impl, m) for m in _CAPABILITY_METHODS[cap_id])
        caps.append(Capability(id=cap_id, state="supported" if served else "unimplemented"))
    return caps


def _gate_error(cap_id: str, state: CapabilityState | None) -> StorageApiError:
    """The error a gated (non-``supported``) surface raises, by state."""
    if state == "unavailable":
        return UnavailableError(f"{cap_id} is currently unavailable")
    if state == "disabled":
        return NotSupportedError(f"{cap_id} is disabled by configuration")
    return NotSupportedError(f"{cap_id} is not implemented by this backend")


class _ServedProvider(StorageProvider):
    """A composed ``StorageProvider``: advertises resolved capabilities and gates them.

    Wraps an ``Implementation`` with the precomputed ``ProviderProperties`` and
    per-id effective states. Each surface gate-checks its capability first (a
    non-``supported`` state raises the matching error) then delegates to the
    impl. Composite getters delegate to the impl, whose base delegation rides on
    the impl's own ``list_*``.
    """

    def __init__(self, impl: StorageProvider, props: ProviderProperties, capabilities: list[Capability]) -> None:
        self._impl = impl
        self._props = props
        self._states = {cap.id: cap.state for cap in capabilities}

    def _gate(self, cap_id: str) -> None:
        state = self._states.get(cap_id)
        if state != "supported":
            raise _gate_error(cap_id, state)

    def properties(self) -> ProviderProperties:
        return self._props

    def health_check(self) -> None:
        self._impl.health_check()

    def list_tenants(self, req: ListTenantsRequest) -> ListTenantsResponse:
        self._gate(CAP_TENANT_LIST)
        return self._impl.list_tenants(req)

    def get_tenant(self, req: GetTenantRequest) -> Tenant:
        self._gate(CAP_TENANT_GET)
        return self._impl.get_tenant(req)

    def get_tenant_quota(self, req: GetTenantQuotaRequest) -> TenantQuota:
        self._gate(CAP_TENANT_GET_QUOTA)
        return self._impl.get_tenant_quota(req)

    def list_tenant_quotas(self, req: ListTenantQuotasRequest) -> ListTenantQuotasResponse:
        self._gate(CAP_TENANT_LIST_QUOTAS)
        return self._impl.list_tenant_quotas(req)

    def create_volume(self, req: CreateVolumeRequest) -> Volume:
        self._gate(CAP_VOLUME_CREATE)
        return self._impl.create_volume(req)

    def delete_volume(self, req: DeleteVolumeRequest) -> None:
        self._gate(CAP_VOLUME_DELETE)
        self._impl.delete_volume(req)

    def list_volumes(self, req: ListVolumesRequest) -> ListVolumesResponse:
        self._gate(CAP_VOLUME_LIST)
        return self._impl.list_volumes(req)

    def get_volume(self, req: GetVolumeRequest) -> Volume:
        self._gate(CAP_VOLUME_GET)
        return self._impl.get_volume(req)

    def list_directory_quotas(self, req: ListDirectoryQuotasRequest) -> ListDirectoryQuotasResponse:
        self._gate(CAP_DIRECTORY_QUOTA_LIST)
        return self._impl.list_directory_quotas(req)

    def get_directory_quota(self, req: GetDirectoryQuotaRequest) -> DirectoryQuota:
        self._gate(CAP_DIRECTORY_QUOTA_GET)
        return self._impl.get_directory_quota(req)

    def set_directory_quota(self, req: SetDirectoryQuotaRequest) -> DirectoryQuota:
        self._gate(CAP_DIRECTORY_QUOTA_SET)
        return self._impl.set_directory_quota(req)

    def delete_directory_quota(self, req: DeleteDirectoryQuotaRequest) -> None:
        self._gate(CAP_DIRECTORY_QUOTA_DELETE)
        self._impl.delete_directory_quota(req)

    def list_user_quotas(self, req: ListUserQuotasRequest) -> ListUserQuotasResponse:
        self._gate(CAP_USER_QUOTA_LIST)
        return self._impl.list_user_quotas(req)

    def get_user_quota(self, req: GetUserQuotaRequest) -> UserQuota:
        self._gate(CAP_USER_QUOTA_GET)
        return self._impl.get_user_quota(req)

    def set_user_quota(self, req: SetUserQuotaRequest) -> UserQuota:
        self._gate(CAP_USER_QUOTA_SET)
        return self._impl.set_user_quota(req)

    def delete_user_quota(self, req: DeleteUserQuotaRequest) -> None:
        self._gate(CAP_USER_QUOTA_DELETE)
        self._impl.delete_user_quota(req)


def _with_default_tenant_req(req: object, default_tenant: str) -> object:
    """Inject ``default_tenant`` where a request left the tenant unspecified.

    Fills a top-level ``tenant_id`` that is ``None``, or a nested ``quota``'s
    empty ``tenant_id`` (the set-quota requests carry tenant inside the record).
    """
    if hasattr(req, "tenant_id") and getattr(req, "tenant_id") is None:
        return replace(req, tenant_id=default_tenant)  # type: ignore[type-var]
    quota = getattr(req, "quota", None)
    if quota is not None and getattr(quota, "tenant_id", None) in (None, ""):
        return replace(req, quota=replace(quota, tenant_id=default_tenant))  # type: ignore[type-var]
    return req


class _DefaultTenantApi(StorageProvider):
    """Wrap a ``StorageProvider`` to resolve unspecified tenants to a fixed default.

    A single-tenant provider sets one default here so callers never pass
    ``tenant_id``; a request that DOES name a tenant is untouched. ``list_tenants``
    and ``health_check`` are not tenant-scoped and pass straight through.
    """

    def __init__(self, inner: StorageProvider, default_tenant: str) -> None:
        self._inner = inner
        self._default = default_tenant

    def _wt(self, req: object) -> object:
        return _with_default_tenant_req(req, self._default)

    def properties(self) -> ProviderProperties:
        return self._inner.properties()

    def health_check(self) -> None:
        self._inner.health_check()

    def list_tenants(self, req: ListTenantsRequest) -> ListTenantsResponse:
        return self._inner.list_tenants(req)

    def get_tenant(self, req: GetTenantRequest) -> Tenant:
        return self._inner.get_tenant(self._wt(req))  # type: ignore[arg-type]

    def get_tenant_quota(self, req: GetTenantQuotaRequest) -> TenantQuota:
        return self._inner.get_tenant_quota(self._wt(req))  # type: ignore[arg-type]

    def list_tenant_quotas(self, req: ListTenantQuotasRequest) -> ListTenantQuotasResponse:
        return self._inner.list_tenant_quotas(self._wt(req))  # type: ignore[arg-type]

    def create_volume(self, req: CreateVolumeRequest) -> Volume:
        return self._inner.create_volume(self._wt(req))  # type: ignore[arg-type]

    def delete_volume(self, req: DeleteVolumeRequest) -> None:
        self._inner.delete_volume(self._wt(req))  # type: ignore[arg-type]

    def list_volumes(self, req: ListVolumesRequest) -> ListVolumesResponse:
        return self._inner.list_volumes(self._wt(req))  # type: ignore[arg-type]

    def get_volume(self, req: GetVolumeRequest) -> Volume:
        return self._inner.get_volume(self._wt(req))  # type: ignore[arg-type]

    def list_directory_quotas(self, req: ListDirectoryQuotasRequest) -> ListDirectoryQuotasResponse:
        return self._inner.list_directory_quotas(self._wt(req))  # type: ignore[arg-type]

    def get_directory_quota(self, req: GetDirectoryQuotaRequest) -> DirectoryQuota:
        return self._inner.get_directory_quota(self._wt(req))  # type: ignore[arg-type]

    def set_directory_quota(self, req: SetDirectoryQuotaRequest) -> DirectoryQuota:
        return self._inner.set_directory_quota(self._wt(req))  # type: ignore[arg-type]

    def delete_directory_quota(self, req: DeleteDirectoryQuotaRequest) -> None:
        self._inner.delete_directory_quota(self._wt(req))  # type: ignore[arg-type]

    def list_user_quotas(self, req: ListUserQuotasRequest) -> ListUserQuotasResponse:
        return self._inner.list_user_quotas(self._wt(req))  # type: ignore[arg-type]

    def get_user_quota(self, req: GetUserQuotaRequest) -> UserQuota:
        return self._inner.get_user_quota(self._wt(req))  # type: ignore[arg-type]

    def set_user_quota(self, req: SetUserQuotaRequest) -> UserQuota:
        return self._inner.set_user_quota(self._wt(req))  # type: ignore[arg-type]

    def delete_user_quota(self, req: DeleteUserQuotaRequest) -> None:
        self._inner.delete_user_quota(self._wt(req))  # type: ignore[arg-type]


def with_default_tenant(api: StorageProvider, default_tenant: str) -> StorageProvider:
    """Wrap ``api`` so unspecified tenants resolve to ``default_tenant``.

    Returns ``api`` unchanged when ``default_tenant`` is empty (no default
    configured - callers must name the tenant explicitly).
    """
    if not default_tenant:
        return api
    return _DefaultTenantApi(api, default_tenant)


def new_implementation(
    core: ProviderProperties,
    impl: Implementation,
    *,
    configured_capability_overrides: Mapping[str, bool] | None = None,
    default_tenant: str = "",
) -> StorageProvider:
    """Compose a served ``StorageProvider`` from an author's ``Implementation``.

    Pipeline (all pure, computed once): detect served surfaces from ``impl`` ->
    apply ``configured_capability_overrides`` (config enable/disable; cannot
    resurrect an unimplemented surface) -> merge the ``capability_qualifiers``
    hook's per-node qualifiers and narrow runtime states -> advertise the result
    on ``properties()`` and gate every surface. Optionally wrap with
    ``with_default_tenant``.
    """
    detected = _detect_capabilities(impl)
    view = ImplementationCapabilities()
    impl.capability_qualifiers(view)
    quals, states = view._collected()
    composed = _compose_capabilities(detected, configured_capability_overrides or {}, quals)
    narrowed = _narrow_states(composed, states)
    props = replace(
        core,
        instance_id=instance_or_default(core.instance_id),
        _capability_list=narrowed,
        backend_metadata=impl.backend_metadata(),
    )
    served = _ServedProvider(impl, props, narrowed)
    return with_default_tenant(served, default_tenant)
