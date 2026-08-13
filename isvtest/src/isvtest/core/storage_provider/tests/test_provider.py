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

"""Unit tests for the ``Implementation`` / ``new_implementation()`` authoring model.

Covers capability detection from the overridden method set, gating (a
non-``supported`` surface raises the matching error), the default-tenant wrapper,
and qualifier / runtime-state composition via the ``capability_qualifiers`` hook.
"""

from __future__ import annotations

import pytest

from isvtest.core.storage_provider import (
    API_VERSION,
    CAP_TENANT_GET_QUOTA,
    CAP_TENANT_LIST,
    CAP_VOLUME_CREATE,
    CAP_VOLUME_GET,
    CAP_VOLUME_LIST,
    QUAL_TIERED,
    CreateVolumeRequest,
    GetTenantQuotaRequest,
    GetVolumeRequest,
    Implementation,
    ImplementationCapabilities,
    ListVolumesRequest,
    ListVolumesResponse,
    NotFoundError,
    NotSupportedError,
    ProviderProperties,
    TenantQuota,
    UnavailableError,
    VersionMetadata,
    new_implementation,
    with_default_tenant,
)


def _core() -> ProviderProperties:
    return ProviderProperties(
        provider_namespace="test.nvidia.com",
        provider_id="test",
        provider_metadata=VersionMetadata(vendor_name="NVIDIA", name="Test", version="0.1.0"),
        sdk_version=API_VERSION,
        storage_type="file",
        storage_protocols=["nfsv4"],
    )


class _QuotaVolumeImpl(Implementation):
    """Backs tenant-quota + volume read only (the managed-K8s shape)."""

    def health_check(self) -> None:
        return None

    def get_tenant_quota(self, req: GetTenantQuotaRequest) -> TenantQuota:
        return TenantQuota(tenant_id=req.tenant_id or "", hard_limit_bytes=100, used_bytes=0, name="t")

    def list_volumes(self, req: ListVolumesRequest) -> ListVolumesResponse:
        return ListVolumesResponse()


def _states(api) -> dict[str, str | None]:
    return {cap.id: cap.state for cap in api.properties().capabilities().raw_list()}


class TestDetection:
    def test_overridden_methods_are_supported(self) -> None:
        api = new_implementation(core=_core(), impl=_QuotaVolumeImpl())
        states = _states(api)
        assert states[CAP_TENANT_GET_QUOTA] == "supported"
        assert states[CAP_VOLUME_LIST] == "supported"

    def test_composite_getters_ride_their_list_sibling(self) -> None:
        # volume.get is served because list_volumes is (base get_volume delegates).
        api = new_implementation(core=_core(), impl=_QuotaVolumeImpl())
        assert _states(api)[CAP_VOLUME_GET] == "supported"

    def test_unimplemented_methods_are_unimplemented(self) -> None:
        states = _states(new_implementation(core=_core(), impl=_QuotaVolumeImpl()))
        assert states[CAP_TENANT_LIST] == "unimplemented"
        assert states[CAP_VOLUME_CREATE] == "unimplemented"


class TestGating:
    def test_unimplemented_surface_raises_not_supported(self) -> None:
        api = new_implementation(core=_core(), impl=_QuotaVolumeImpl())
        with pytest.raises(NotSupportedError, match="not implemented"):
            api.create_volume(CreateVolumeRequest(size_bytes=1, volume_type="file"))

    def test_supported_surface_answers(self) -> None:
        api = new_implementation(core=_core(), impl=_QuotaVolumeImpl())
        assert api.list_volumes(ListVolumesRequest()).volumes == ()
        # The composite getter delegates through and surfaces the real miss.
        with pytest.raises(NotFoundError):
            api.get_volume(GetVolumeRequest(volume_id="missing"))

    def test_config_override_disables_a_supported_surface(self) -> None:
        api = new_implementation(
            core=_core(),
            impl=_QuotaVolumeImpl(),
            configured_capability_overrides={CAP_VOLUME_LIST: False},
        )
        assert _states(api)[CAP_VOLUME_LIST] == "disabled"
        with pytest.raises(NotSupportedError, match="disabled by configuration"):
            api.list_volumes(ListVolumesRequest())

    def test_config_override_cannot_resurrect_unimplemented(self) -> None:
        # A config "enable" can flip disabled->supported but never conjure a
        # surface the code does not serve.
        api = new_implementation(
            core=_core(),
            impl=_QuotaVolumeImpl(),
            configured_capability_overrides={CAP_VOLUME_CREATE: True},
        )
        assert _states(api)[CAP_VOLUME_CREATE] == "unimplemented"
        with pytest.raises(NotSupportedError):
            api.create_volume(CreateVolumeRequest(size_bytes=1, volume_type="file"))

    def test_hook_narrows_supported_to_unavailable(self) -> None:
        class _Impl(_QuotaVolumeImpl):
            def capability_qualifiers(self, caps: ImplementationCapabilities) -> None:
                caps.volume().list().set_state("unavailable")

        api = new_implementation(core=_core(), impl=_Impl())
        assert _states(api)[CAP_VOLUME_LIST] == "unavailable"
        with pytest.raises(UnavailableError, match="currently unavailable"):
            api.list_volumes(ListVolumesRequest())

    def test_hook_cannot_re_enable_unimplemented(self) -> None:
        class _Impl(_QuotaVolumeImpl):
            def capability_qualifiers(self, caps: ImplementationCapabilities) -> None:
                # More available than the detected state -> ignored.
                caps.get(CAP_VOLUME_CREATE).set_state("supported")

        api = new_implementation(core=_core(), impl=_Impl())
        assert _states(api)[CAP_VOLUME_CREATE] == "unimplemented"


class TestDefaultTenant:
    def test_injects_default_when_unspecified(self) -> None:
        api = new_implementation(core=_core(), impl=_QuotaVolumeImpl(), default_tenant="t-def")
        assert api.get_tenant_quota(GetTenantQuotaRequest()).tenant_id == "t-def"

    def test_preserves_explicit_tenant(self) -> None:
        api = new_implementation(core=_core(), impl=_QuotaVolumeImpl(), default_tenant="t-def")
        assert api.get_tenant_quota(GetTenantQuotaRequest(tenant_id="other")).tenant_id == "other"

    def test_no_default_leaves_tenant_unset(self) -> None:
        api = new_implementation(core=_core(), impl=_QuotaVolumeImpl(), default_tenant="")
        # Not wrapped: the impl sees the request verbatim (tenant_id None -> "").
        assert api.get_tenant_quota(GetTenantQuotaRequest()).tenant_id == ""

    def test_with_default_tenant_is_noop_when_empty(self) -> None:
        api = new_implementation(core=_core(), impl=_QuotaVolumeImpl())
        assert with_default_tenant(api, "") is api


class TestQualifierComposition:
    def test_group_qualifier_inherits_to_leaf(self) -> None:
        class _Impl(_QuotaVolumeImpl):
            def capability_qualifiers(self, caps: ImplementationCapabilities) -> None:
                caps.tenant().set_tiered(True)

        props = new_implementation(core=_core(), impl=_Impl()).properties()
        caps = props.capabilities()
        cap = caps.get_tenant_quota()
        assert cap.qualifiers()[QUAL_TIERED] == "true"
        assert caps.tenant().get_quota().tiered() is True

    def test_qualifier_dropped_on_unimplemented_surface(self) -> None:
        class _Impl(_QuotaVolumeImpl):
            def capability_qualifiers(self, caps: ImplementationCapabilities) -> None:
                # quota.directory is not served -> its qualifiers are cleared.
                caps.quota().directory().set_inodes(True)

        props = new_implementation(core=_core(), impl=_Impl()).properties()
        tree = props.capabilities()
        assert tree.quota().directory().set().state() == "unimplemented"
