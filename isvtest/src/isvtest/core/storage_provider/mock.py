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

"""In-memory ``MockStorageApi`` reference implementation.

Used by the unit tests for the validation suite so validators can be exercised
end-to-end without a real backend. Authored on ``Implementation``; tests that
need the composed ``properties()`` / capability gating serve it through
``new_implementation()`` (see ``test_storage_provider.py``).

Which surfaces the mock backs is selected by composition, not config:
``MockStorageApi`` mixes in the directory- and user-quota surfaces (so they
answer), while a test that needs a narrower backend composes a mock from a
subset of the mixins (``_MockCore``, ``_DirectoryQuotaMixin``,
``_UserQuotaMixin``, and their list-less variants); a surface whose method is
absent falls back to the base ``StorageProvider`` method, which raises
``NotSupportedError`` - exactly what the validation suite probes for. Behaviour
within a backed surface is tuned by the L2 qualifiers passed to ``__init__``.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime

from isvtest.core.storage_provider.api import (
    API_VERSION,
    CAP_DIRECTORY_QUOTA_SET,
    CAP_USER_QUOTA_SET,
    QUAL_BYTE_GRANULARITY,
    QUAL_DEFAULT_USER_SLOT,
    QUAL_ID_ASSIGNMENT,
    QUAL_INODES,
    QUAL_MULTI_PATH_BINDING,
    AuthenticationError,
    ConflictError,
    CreateVolumeRequest,
    DeleteDirectoryQuotaRequest,
    DeleteUserQuotaRequest,
    DeleteVolumeRequest,
    DirectoryQuota,
    GetTenantQuotaRequest,
    Implementation,
    ImplementationCapabilities,
    ListDirectoryQuotasRequest,
    ListDirectoryQuotasResponse,
    ListTenantQuotasRequest,
    ListTenantQuotasResponse,
    ListTenantsRequest,
    ListTenantsResponse,
    ListUserQuotasRequest,
    ListUserQuotasResponse,
    ListVolumesRequest,
    ListVolumesResponse,
    NotFoundError,
    NotSupportedError,
    ProviderProperties,
    QuotaExceededError,
    QuotaLimits,
    QuotaUsage,
    SetDirectoryQuotaRequest,
    SetUserQuotaRequest,
    TagFilter,
    Tenant,
    TenantQuota,
    UserQuota,
    ValidationError,
    VersionMetadata,
    Volume,
    _resolve_qualifiers,
)


def default_mock_core() -> ProviderProperties:
    """VAST-shape default core for the mock (identity only; caps are derived)."""
    return ProviderProperties(
        provider_namespace="mock.nvidia.com",
        provider_id="mock",
        provider_metadata=VersionMetadata(vendor_name="NVIDIA", name="Mock", version="0.1.0"),
        sdk_version=API_VERSION,
        storage_type="file",
        storage_protocols=["mock"],
    )


def _normalize_quota_hard(
    hard: QuotaLimits | None,
    *,
    byte_granularity: int | None,
    inodes_supported: bool,
) -> QuotaLimits | None:
    """Apply the backend's storage rules to caller-supplied ``hard`` caps.

    * ``byte_granularity`` (when non-None) ceil-rounds ``hard.bytes`` to the
      declared alignment so the returned DTO reflects the actual stored value.
    * ``hard.inodes`` is dropped to ``None`` when the backend does not support an
      inode dimension.
    """
    if hard is None:
        return None
    bytes_value = hard.bytes
    if bytes_value is not None and byte_granularity is not None:
        bytes_value = ((bytes_value + byte_granularity - 1) // byte_granularity) * byte_granularity
    inodes_value = hard.inodes if inodes_supported else None
    return QuotaLimits(bytes=bytes_value, inodes=inodes_value)


def _tag_matches(tags: Mapping[str, str], f: TagFilter) -> bool:
    if f.key not in tags:
        return False
    if not f.values:
        return True
    return tags[f.key] in f.values


class _MockCore(Implementation):
    """Required core + tenant + volume surfaces, with the in-memory state.

    The quota surfaces live in the mixins so a test can compose a mock that does
    not back them (their methods then fall back to the base raise).
    """

    def __init__(
        self,
        *,
        tenant_id: str = "mock-tenant",
        tenant_name: str = "mock tenant",
        hard_limit_bytes: int = 100 * 1024**3,
        healthy: bool = True,
        core: ProviderProperties | None = None,
        qualifiers: Mapping[str, Mapping[str, str]] | None = None,
    ) -> None:
        self._core = core or default_mock_core()
        self._qualifiers = {k: dict(v) for k, v in (qualifiers or {}).items()}
        self._default_tenant = tenant_id
        self._tenant_name = tenant_name
        self._hard_limit_bytes = hard_limit_bytes
        self.healthy = healthy
        if self._dir_qual(QUAL_MULTI_PATH_BINDING, "false") == "true":
            raise NotImplementedError(
                "MockStorageApi does not yet implement "
                "QUAL_MULTI_PATH_BINDING='true'; leave it unset or subclass to "
                "add the multi-binding semantics your test needs."
            )
        self._volumes: dict[str, Volume] = {}
        self._directory_quotas: dict[tuple[str, str], list[DirectoryQuota]] = {}
        self._user_quotas: dict[tuple[str, str], dict[str | None, UserQuota]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Capability / qualifier helpers (read off the composed properties())
    # ------------------------------------------------------------------

    def capability_qualifiers(self, caps: ImplementationCapabilities) -> None:
        # Re-express the dict-shaped qualifiers this mock was built with onto the
        # typed write view. A group id (e.g. ``quota.directory``) fans down to its
        # leaves the same way ``_resolve_qualifiers`` does when composing.
        for node_id, kv in self._qualifiers.items():
            node = caps.get(node_id)
            for key, value in kv.items():
                node.set_qualifier(key, value)

    def backend_metadata(self) -> VersionMetadata | None:
        return self._core.backend_metadata

    def _qual(self, cap_id: str, key: str, default: str | None) -> str | None:
        # Resolve group-inherited qualifiers the same way properties() does.
        return _resolve_qualifiers(self._qualifiers, cap_id).get(key, default)

    def _dir_qual(self, key: str, default: str | None) -> str | None:
        return self._qual(CAP_DIRECTORY_QUOTA_SET, key, default)

    def _user_qual(self, key: str, default: str | None) -> str | None:
        return self._qual(CAP_USER_QUOTA_SET, key, default)

    @staticmethod
    def _byte_granularity(value: str | None) -> int | None:
        return int(value) if value else None

    def _resolve_tenant(self, tenant_id: str | None) -> str:
        resolved = tenant_id or self._default_tenant
        if resolved != self._default_tenant:
            raise NotFoundError(f"tenant {resolved!r} not found (mock has only {self._default_tenant!r})")
        return resolved

    # ------------------------------------------------------------------
    # Required core
    # ------------------------------------------------------------------

    def health_check(self) -> None:
        if not self.healthy:
            raise AuthenticationError("mock backend marked unhealthy")

    def list_tenants(self, req: ListTenantsRequest) -> ListTenantsResponse:
        tenant = Tenant(id=self._default_tenant, name=self._tenant_name)
        if not req.ids:
            return ListTenantsResponse(tenants=(tenant,))
        wanted = set(req.ids)
        return ListTenantsResponse(tenants=(tenant,) if tenant.id in wanted else ())

    def get_tenant_quota(self, req: GetTenantQuotaRequest) -> TenantQuota:
        resolved = self._resolve_tenant(req.tenant_id)
        with self._lock:
            used = sum(v.size_bytes for v in self._volumes.values() if v.tenant_id == resolved)
        return TenantQuota(
            tenant_id=resolved,
            hard_limit_bytes=self._hard_limit_bytes,
            used_bytes=used,
            name=self._tenant_name,
        )

    def list_tenant_quotas(self, req: ListTenantQuotasRequest) -> ListTenantQuotasResponse:
        # Untiered backend: a single aggregate entry, equivalent to get_tenant_quota.
        quota = self.get_tenant_quota(GetTenantQuotaRequest(tenant_id=req.tenant_id))
        return ListTenantQuotasResponse(tenant_quotas=(quota,))

    # ------------------------------------------------------------------
    # Volumes
    # ------------------------------------------------------------------

    def create_volume(self, req: CreateVolumeRequest) -> Volume:
        resolved = self._resolve_tenant(req.tenant_id)
        with self._lock:
            used = sum(v.size_bytes for v in self._volumes.values() if v.tenant_id == resolved)
            if used + req.size_bytes > self._hard_limit_bytes:
                raise QuotaExceededError(
                    f"create_volume would exceed tenant quota: {used + req.size_bytes} > {self._hard_limit_bytes}"
                )
            volume = Volume(
                tenant_id=resolved,
                id=f"vol-{uuid.uuid4().hex[:12]}",
                size_bytes=req.size_bytes,
                created_at=datetime.now(UTC),
                type=req.volume_type,
                state="available",
                name=req.name,
                tier=req.tier,
                tags=dict(req.tags or {}),
                used_bytes=0,
                available_bytes=req.size_bytes,
            )
            self._volumes[volume.id] = volume
            return volume

    def delete_volume(self, req: DeleteVolumeRequest) -> None:
        self._resolve_tenant(req.tenant_id)
        with self._lock:
            self._volumes.pop(req.volume_id, None)

    def list_volumes(self, req: ListVolumesRequest) -> ListVolumesResponse:
        resolved = self._resolve_tenant(req.tenant_id)
        wanted_ids = set(req.ids) if req.ids else None
        filters = list(req.tag_filters)
        with self._lock:
            volumes = list(self._volumes.values())
        result: list[Volume] = []
        for vol in volumes:
            if vol.tenant_id != resolved:
                continue
            if wanted_ids is not None and vol.id not in wanted_ids:
                continue
            if not all(_tag_matches(vol.tags, f) for f in filters):
                continue
            result.append(vol)
        return ListVolumesResponse(volumes=tuple(result))


class _DirectoryQuotaSetOnlyMixin:
    """``set`` + ``delete`` directory-quota surfaces (Lustre-shape: no list)."""

    def set_directory_quota(self: _MockCore, req: SetDirectoryQuotaRequest) -> DirectoryQuota:
        quota = req.quota
        resolved = self._resolve_tenant(quota.tenant_id)
        id_assignment = self._dir_qual(QUAL_ID_ASSIGNMENT, "backend")

        if id_assignment == "caller" and quota.id is None:
            raise ValidationError("directory quota id is required when id_assignment='caller'")
        if id_assignment == "backend" and quota.path is None:
            raise ValidationError("directory quota path is required when id_assignment='backend'")

        new_hard = _normalize_quota_hard(
            quota.hard,
            byte_granularity=self._byte_granularity(self._dir_qual(QUAL_BYTE_GRANULARITY, None)),
            inodes_supported=self._dir_qual(QUAL_INODES, "true") != "false",
        )
        natural_attr = "id" if id_assignment == "caller" else "path"
        natural_value = getattr(quota, natural_attr)

        with self._lock:
            records = self._directory_quotas.setdefault((resolved, quota.volume_id), [])
            match_idx = next(
                (i for i, r in enumerate(records) if getattr(r, natural_attr) == natural_value),
                None,
            )
            if id_assignment == "backend" and quota.id is None:
                new_id = records[match_idx].id if match_idx is not None else f"dq-{uuid.uuid4().hex[:8]}"
            else:
                new_id = quota.id
            stored = replace(
                quota,
                tenant_id=resolved,
                id=new_id,
                hard=new_hard,
                usage=QuotaUsage(),
                attributes=dict(quota.attributes),
            )
            if match_idx is not None:
                records[match_idx] = stored
            else:
                records.append(stored)
            return stored

    def delete_directory_quota(self: _MockCore, req: DeleteDirectoryQuotaRequest) -> None:
        if req.path is None and req.id is None:
            raise ValidationError("delete_directory_quota requires at least one of `path` or `id`")
        resolved = self._resolve_tenant(req.tenant_id)
        with self._lock:
            records = self._directory_quotas.get((resolved, req.volume_id))
            if not records:
                return
            # Scan the whole list so a full match always wins over a partial
            # (one-key) disagreement regardless of order.
            full_idx: int | None = None
            partial: DirectoryQuota | None = None
            for i, r in enumerate(records):
                path_match = req.path is None or r.path == req.path
                id_match = req.id is None or r.id == req.id
                if path_match and id_match:
                    full_idx = i
                    break
                if req.path is not None and req.id is not None and (r.path == req.path or r.id == req.id):
                    partial = r
            if full_idx is not None:
                del records[full_idx]
                return
            if partial is not None:
                raise ConflictError(
                    f"directory quota lookup mismatch on volume {req.volume_id!r}: "
                    f"requested path={req.path!r}, id={req.id!r}; "
                    f"found path={partial.path!r}, id={partial.id!r}"
                )


class _DirectoryQuotaMixin(_DirectoryQuotaSetOnlyMixin):
    """Full directory-quota surface (list + the default-delegated get + set/delete)."""

    def list_directory_quotas(self: _MockCore, req: ListDirectoryQuotasRequest) -> ListDirectoryQuotasResponse:
        resolved = self._resolve_tenant(req.tenant_id)
        with self._lock:
            return ListDirectoryQuotasResponse(
                directory_quotas=tuple(self._directory_quotas.get((resolved, req.volume_id), []))
            )


class _UserQuotaSetOnlyMixin:
    """``set`` + ``delete`` user-quota surfaces (Lustre-shape: no list)."""

    def set_user_quota(self: _MockCore, req: SetUserQuotaRequest) -> UserQuota:
        quota = req.quota
        if quota.user is None and self._user_qual(QUAL_DEFAULT_USER_SLOT, "true") == "false":
            raise NotSupportedError("default-user slot (user=None) not supported by this mock")
        resolved = self._resolve_tenant(quota.tenant_id)

        new_hard = _normalize_quota_hard(
            quota.hard,
            byte_granularity=self._byte_granularity(self._user_qual(QUAL_BYTE_GRANULARITY, None)),
            inodes_supported=self._user_qual(QUAL_INODES, "true") != "false",
        )
        stored = replace(
            quota,
            tenant_id=resolved,
            hard=new_hard,
            usage=QuotaUsage(),
            attributes=dict(quota.attributes),
        )
        with self._lock:
            inner = self._user_quotas.setdefault((resolved, quota.volume_id), {})
            inner[quota.user] = stored
            return stored

    def delete_user_quota(self: _MockCore, req: DeleteUserQuotaRequest) -> None:
        if req.user is None and self._user_qual(QUAL_DEFAULT_USER_SLOT, "true") == "false":
            raise NotSupportedError("default-user slot (user=None) not supported by this mock")
        resolved = self._resolve_tenant(req.tenant_id)
        with self._lock:
            inner = self._user_quotas.get((resolved, req.volume_id))
            if inner is None:
                return
            inner.pop(req.user, None)


class _UserQuotaMixin(_UserQuotaSetOnlyMixin):
    """Full user-quota surface (list + the default-delegated get + set/delete)."""

    def list_user_quotas(self: _MockCore, req: ListUserQuotasRequest) -> ListUserQuotasResponse:
        resolved = self._resolve_tenant(req.tenant_id)
        with self._lock:
            return ListUserQuotasResponse(
                user_quotas=tuple(self._user_quotas.get((resolved, req.volume_id), {}).values())
            )


class MockStorageApi(_DirectoryQuotaMixin, _UserQuotaMixin, _MockCore):
    """Single-tenant in-memory ``StorageProvider`` for tests and templates.

    Construct with ``MockStorageApi(tenant_id="t-1", hard_limit_bytes=...)`` to
    populate the default tenant. Toggle ``healthy=False`` to make
    ``health_check`` raise ``AuthenticationError``.

    Backs both the directory- and user-quota surfaces (it mixes both in).
    Pass ``qualifiers={CAP_GROUP_DIRECTORY_QUOTA: {QUAL_ID_ASSIGNMENT: "caller"}}``
    to tune L2 semantic facts (id assignment, byte granularity, inode support,
    default-user slot). A test that needs a backend WITHOUT a surface composes a
    narrower mock from the mixins (e.g. ``class _NoDirectory(_UserQuotaMixin,
    _MockCore)``) rather than toggling a flag - a surface whose method is absent
    falls back to the base raise (``NotSupportedError``). The default is a
    permissive VAST-shape: backend-assigned ids,
    byte-exact granularity, inode dimension on, default-user slot on.
    ``QUAL_MULTI_PATH_BINDING="true"`` is not implemented by this mock.
    """
