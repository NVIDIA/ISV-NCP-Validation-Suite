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

"""Unit tests for ``isvtest.core.storage_provider.api``.

Cover ABC abstractness, the request/response surface defaults, the
capability/qualifier model, the error taxonomy, and dataclass invariants. The
``Implementation`` / ``new_implementation()`` composition is exercised in
``test_provider.py``; the ``MockStorageApi`` exercise lives in ``test_mock.py``.
"""

from __future__ import annotations

import dataclasses

import pytest

from isvtest.core.storage_provider import (
    API_VERSION,
    CAP_DIRECTORY_QUOTA_SET,
    CAP_USER_QUOTA_SET,
    CAP_VOLUME_CREATE,
    CAPABILITY_IDS,
    DEFAULT_INSTANCE_ID,
    QUAL_ID_ASSIGNMENT,
    AuthenticationError,
    Capability,
    ConflictError,
    CreateVolumeRequest,
    CsiSpec,
    DeleteVolumeRequest,
    DirectoryQuota,
    GetDirectoryQuotaRequest,
    GetTenantQuotaRequest,
    GetTenantRequest,
    GetUserQuotaRequest,
    GetVolumeRequest,
    ListDirectoryQuotasRequest,
    ListTenantQuotasRequest,
    ListTenantsRequest,
    ListTenantsResponse,
    ListUserQuotasRequest,
    ListVolumesRequest,
    ListVolumesResponse,
    MountSpec,
    NotFoundError,
    NotSupportedError,
    ProviderProperties,
    QuotaExceededError,
    QuotaLimits,
    QuotaUsage,
    SetDirectoryQuotaRequest,
    SetUserQuotaRequest,
    StorageApiError,
    StorageProvider,
    TagFilter,
    Tenant,
    TenantQuota,
    UnavailableError,
    UserQuota,
    ValidationError,
    VersionMetadata,
    Volume,
    instance_or_default,
)


def _all_caps() -> list[Capability]:
    """Every registry id as a qualifier-free ``Capability`` entry (test data)."""
    return [Capability(id=cid) for cid in CAPABILITY_IDS]


def _props(**overrides) -> ProviderProperties:
    """Minimal VAST-shape ProviderProperties for test fixtures (all caps present)."""
    base = {
        "provider_namespace": "test.nvidia.com",
        "provider_id": "test",
        "provider_metadata": VersionMetadata(vendor_name="NVIDIA", name="Test", version="0.1.0"),
        "sdk_version": API_VERSION,
        "storage_type": "file",
        "storage_protocols": ["nfsv4"],
        "_capability_list": _all_caps(),
    }
    base.update(overrides)
    return ProviderProperties(**base)


def _cap(props: ProviderProperties, cap_id: str) -> Capability | None:
    """The advertised ``Capability`` record for ``cap_id``, or ``None``."""
    for cap in props.capabilities().raw_list():
        if cap.id == cap_id:
            return cap
    return None


class _Minimal(StorageProvider):
    """Concrete shim implementing only the three required methods."""

    def properties(self) -> ProviderProperties:
        return _props()

    def health_check(self) -> None:
        return None

    def get_tenant_quota(self, req: GetTenantQuotaRequest) -> TenantQuota:
        return TenantQuota(tenant_id=req.tenant_id or "t", hard_limit_bytes=1, used_bytes=0, name="n")

    def list_volumes(self, req: ListVolumesRequest) -> ListVolumesResponse:
        return ListVolumesResponse()


class TestAbcSurface:
    def test_api_version_is_v1alpha1(self) -> None:
        assert API_VERSION == "v1alpha1"

    def test_storage_api_cannot_be_instantiated_directly(self) -> None:
        with pytest.raises(TypeError):
            StorageProvider()  # type: ignore[abstract]

    def test_subclass_missing_abstract_methods_cannot_instantiate(self) -> None:
        class Incomplete(StorageProvider):
            pass

        with pytest.raises(TypeError):
            Incomplete()  # type: ignore[abstract]

    def test_minimal_concrete_subclass_can_instantiate(self) -> None:
        api = _Minimal()
        api.health_check()
        assert api.properties().provider_metadata.name == "Test"
        assert api.get_tenant_quota(GetTenantQuotaRequest(tenant_id="t")).hard_limit_bytes == 1
        assert api.list_volumes(ListVolumesRequest()).volumes == ()

    def test_subclass_missing_properties_cannot_instantiate(self) -> None:
        class NoProperties(StorageProvider):
            def health_check(self) -> None:
                return None

            def get_tenant_quota(self, req):
                return TenantQuota(tenant_id="t", hard_limit_bytes=1, used_bytes=0, name="n")

            def list_volumes(self, req):
                return ListVolumesResponse()

        with pytest.raises(TypeError):
            NoProperties()  # type: ignore[abstract]


class TestOptionalMethodDefaults:
    """The optional methods raise ``NotSupportedError`` by default."""

    def test_list_tenants_default_raises(self) -> None:
        with pytest.raises(NotSupportedError):
            _Minimal().list_tenants(ListTenantsRequest())

    def test_get_tenant_default_raises_when_list_unsupported(self) -> None:
        with pytest.raises(NotSupportedError):
            _Minimal().get_tenant(GetTenantRequest(tenant_id="t"))

    def test_create_volume_default_raises(self) -> None:
        with pytest.raises(NotSupportedError):
            _Minimal().create_volume(CreateVolumeRequest(size_bytes=1, volume_type="file"))

    def test_delete_volume_default_raises(self) -> None:
        with pytest.raises(NotSupportedError):
            _Minimal().delete_volume(DeleteVolumeRequest(volume_id="vol-1"))

    def test_get_volume_default_delegates_to_list_and_raises_not_found(self) -> None:
        with pytest.raises(NotFoundError):
            _Minimal().get_volume(GetVolumeRequest(volume_id="missing"))

    def test_list_tenant_quotas_default_raises(self) -> None:
        with pytest.raises(NotSupportedError):
            _Minimal().list_tenant_quotas(ListTenantQuotasRequest())


class TestGetTenantDefault:
    """The default get_tenant resolves None only when the backend has one tenant."""

    class _OneTenant(_Minimal):
        def list_tenants(self, req: ListTenantsRequest) -> ListTenantsResponse:
            tenants = (Tenant(id="only"),)
            if req.ids:
                tenants = tuple(t for t in tenants if t.id in set(req.ids))
            return ListTenantsResponse(tenants=tenants)

    class _TwoTenants(_Minimal):
        def list_tenants(self, req: ListTenantsRequest) -> ListTenantsResponse:
            tenants = (Tenant(id="a"), Tenant(id="b"))
            if req.ids:
                tenants = tuple(t for t in tenants if t.id in set(req.ids))
            return ListTenantsResponse(tenants=tenants)

    def test_none_returns_sole_tenant(self) -> None:
        assert self._OneTenant().get_tenant(GetTenantRequest()).id == "only"

    def test_none_with_multiple_tenants_is_ambiguous(self) -> None:
        with pytest.raises(ValidationError):
            self._TwoTenants().get_tenant(GetTenantRequest())

    def test_explicit_id_matches(self) -> None:
        assert self._TwoTenants().get_tenant(GetTenantRequest(tenant_id="b")).id == "b"

    def test_explicit_unknown_id_raises_not_found(self) -> None:
        with pytest.raises(NotFoundError):
            self._TwoTenants().get_tenant(GetTenantRequest(tenant_id="nope"))


class TestQuotaMethodDefaults:
    """The directory- and user-quota methods raise by default."""

    class _DirectoryListOnly(_Minimal):
        def list_directory_quotas(self, req: ListDirectoryQuotasRequest):
            from isvtest.core.storage_provider import ListDirectoryQuotasResponse

            return ListDirectoryQuotasResponse(
                directory_quotas=(
                    DirectoryQuota(tenant_id="t", volume_id=req.volume_id, path="/a", id="1"),
                    DirectoryQuota(tenant_id="t", volume_id=req.volume_id, path="/b", id="2"),
                )
            )

    class _UserListOnly(_Minimal):
        def list_user_quotas(self, req: ListUserQuotasRequest):
            from isvtest.core.storage_provider import ListUserQuotasResponse

            return ListUserQuotasResponse(
                user_quotas=(
                    UserQuota(tenant_id="t", volume_id=req.volume_id, user=None),
                    UserQuota(tenant_id="t", volume_id=req.volume_id, user="1001"),
                )
            )

    def test_list_directory_quotas_default_raises(self) -> None:
        with pytest.raises(NotSupportedError):
            _Minimal().list_directory_quotas(ListDirectoryQuotasRequest(volume_id="v"))

    def test_set_directory_quota_default_raises(self) -> None:
        with pytest.raises(NotSupportedError):
            _Minimal().set_directory_quota(
                SetDirectoryQuotaRequest(DirectoryQuota(tenant_id="t", volume_id="v", path="/a"))
            )

    def test_delete_directory_quota_default_raises(self) -> None:
        from isvtest.core.storage_provider import DeleteDirectoryQuotaRequest

        with pytest.raises(NotSupportedError):
            _Minimal().delete_directory_quota(DeleteDirectoryQuotaRequest(volume_id="v", path="/a"))

    def test_get_directory_quota_default_propagates_not_supported(self) -> None:
        with pytest.raises(NotSupportedError):
            _Minimal().get_directory_quota(GetDirectoryQuotaRequest(volume_id="v", path="/a"))

    def test_get_directory_quota_default_requires_path_or_id(self) -> None:
        with pytest.raises(ValidationError):
            self._DirectoryListOnly().get_directory_quota(GetDirectoryQuotaRequest(volume_id="v"))

    def test_get_directory_quota_default_returns_match_via_list(self) -> None:
        q = self._DirectoryListOnly().get_directory_quota(GetDirectoryQuotaRequest(volume_id="v", path="/a"))
        assert q.path == "/a"
        assert q.id == "1"

    def test_get_directory_quota_default_raises_not_found(self) -> None:
        with pytest.raises(NotFoundError):
            self._DirectoryListOnly().get_directory_quota(GetDirectoryQuotaRequest(volume_id="v", path="/missing"))

    def test_get_directory_quota_default_raises_conflict_on_key_disagreement(self) -> None:
        with pytest.raises(ConflictError):
            self._DirectoryListOnly().get_directory_quota(GetDirectoryQuotaRequest(volume_id="v", path="/a", id="2"))

    def test_list_user_quotas_default_raises(self) -> None:
        with pytest.raises(NotSupportedError):
            _Minimal().list_user_quotas(ListUserQuotasRequest(volume_id="v"))

    def test_set_user_quota_default_raises(self) -> None:
        with pytest.raises(NotSupportedError):
            _Minimal().set_user_quota(SetUserQuotaRequest(UserQuota(tenant_id="t", volume_id="v", user="1001")))

    def test_get_user_quota_default_returns_match_via_list(self) -> None:
        q = self._UserListOnly().get_user_quota(GetUserQuotaRequest(volume_id="v", user="1001"))
        assert q.user == "1001"

    def test_get_user_quota_default_returns_default_user_slot(self) -> None:
        q = self._UserListOnly().get_user_quota(GetUserQuotaRequest(volume_id="v", user=None))
        assert q.user is None

    def test_get_user_quota_default_raises_not_found(self) -> None:
        with pytest.raises(NotFoundError):
            self._UserListOnly().get_user_quota(GetUserQuotaRequest(volume_id="v", user="missing"))


class TestCapabilityModel:
    """``Capability`` carries the merged state + L2 qualifiers; read via ``capabilities()``."""

    def test_capability_lookup_and_by_id(self) -> None:
        props = _props(_capability_list=[Capability(id=CAP_USER_QUOTA_SET)])
        cap = _cap(props, CAP_USER_QUOTA_SET)
        assert cap is not None and cap.id == CAP_USER_QUOTA_SET
        assert {c.id for c in props.capabilities().raw_list()} == {CAP_USER_QUOTA_SET}

    def test_capability_absent_returns_none(self) -> None:
        props = _props(_capability_list=[])
        assert _cap(props, CAP_USER_QUOTA_SET) is None

    def test_capability_carries_qualifiers(self) -> None:
        props = _props(
            _capability_list=[Capability(id=CAP_DIRECTORY_QUOTA_SET, qualifiers={QUAL_ID_ASSIGNMENT: "caller"})]
        )
        cap = _cap(props, CAP_DIRECTORY_QUOTA_SET)
        assert cap is not None
        assert cap.qualifiers[QUAL_ID_ASSIGNMENT] == "caller"


class TestInstanceOrDefault:
    def test_instance_or_default_helper(self) -> None:
        assert instance_or_default("") == DEFAULT_INSTANCE_ID
        assert instance_or_default("x") == "x"


class TestErrorTaxonomy:
    @pytest.mark.parametrize(
        "exc_cls",
        [
            AuthenticationError,
            ConflictError,
            NotFoundError,
            NotSupportedError,
            QuotaExceededError,
            UnavailableError,
            ValidationError,
        ],
    )
    def test_concrete_errors_are_storage_api_errors(self, exc_cls: type[Exception]) -> None:
        assert issubclass(exc_cls, StorageApiError)
        with pytest.raises(StorageApiError):
            raise exc_cls("boom")


class TestValueTypeInvariants:
    """All shim value types are frozen dataclasses."""

    @pytest.mark.parametrize(
        "cls",
        [
            Tenant,
            TenantQuota,
            MountSpec,
            CsiSpec,
            Volume,
            TagFilter,
            DirectoryQuota,
            UserQuota,
            QuotaLimits,
            QuotaUsage,
            ProviderProperties,
            VersionMetadata,
            Capability,
        ],
    )
    def test_value_types_are_frozen_dataclasses(self, cls: type) -> None:
        assert dataclasses.is_dataclass(cls)
        assert cls.__dataclass_params__.frozen is True  # type: ignore[attr-defined]

    def test_tag_filter_existence_check_default(self) -> None:
        assert TagFilter(key="k").values == ()

    def test_tenant_minimal_construction(self) -> None:
        t = Tenant(id="t-1")
        assert t.id == "t-1"
        assert t.name is None
        assert t.attributes == {}

    def test_tenant_quota_tier_and_id_default_unset(self) -> None:
        q = TenantQuota(tenant_id="t", hard_limit_bytes=1, used_bytes=0, name="n")
        assert q.tier is None
        assert q.id == ""
        tiered = TenantQuota(
            tenant_id="t",
            hard_limit_bytes=1,
            used_bytes=0,
            name="n",
            tier="PERSISTENT_2",
            id="q-1",
        )
        assert tiered.tier == "PERSISTENT_2"
        assert tiered.id == "q-1"

    def test_quota_limits_and_usage_default_to_unset(self) -> None:
        assert QuotaLimits().bytes is None
        assert QuotaLimits().inodes is None
        assert QuotaLimits(bytes=1024, inodes=10).bytes == 1024
        assert QuotaUsage().bytes is None

    def test_directory_quota_construction(self) -> None:
        q = DirectoryQuota(tenant_id="t", volume_id="v", path="/exports/a", id="42", hard=QuotaLimits(bytes=1024**3))
        assert q.path == "/exports/a"
        assert q.id == "42"
        assert q.hard is not None and q.hard.bytes == 1024**3
        assert q.usage == QuotaUsage()

    def test_user_quota_construction(self) -> None:
        default_slot = UserQuota(tenant_id="t", volume_id="v", user=None)
        assert default_slot.user is None
        assert default_slot.hard is None

    def test_provider_properties_requires_identity(self) -> None:
        props = _props()
        assert props.provider_namespace == "test.nvidia.com"
        assert props.provider_id == "test"
        assert props.provider_metadata.version == "0.1.0"
        assert props.storage_protocols == ["nfsv4"]
        assert _cap(props, CAP_VOLUME_CREATE) is not None

    def test_version_metadata_defaults_empty(self) -> None:
        vm = VersionMetadata()
        assert vm.vendor_name == ""
        assert vm.version == ""
