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

"""End-to-end exercise of ``MockStorageApi`` against the request/response surface."""

from __future__ import annotations

from typing import Literal

import pytest

from isvtest.core.storage_provider import (
    CAP_GROUP_DIRECTORY_QUOTA,
    CAP_GROUP_USER_QUOTA,
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
    GetDirectoryQuotaRequest,
    GetTenantQuotaRequest,
    GetUserQuotaRequest,
    GetVolumeRequest,
    ListDirectoryQuotasRequest,
    ListTenantQuotasRequest,
    ListUserQuotasRequest,
    ListVolumesRequest,
    MockStorageApi,
    NotFoundError,
    NotSupportedError,
    QuotaExceededError,
    QuotaLimits,
    SetDirectoryQuotaRequest,
    SetUserQuotaRequest,
    TagFilter,
    UserQuota,
    ValidationError,
)
from isvtest.core.storage_provider.mock import (
    _DirectoryQuotaMixin,
    _DirectoryQuotaSetOnlyMixin,
    _MockCore,
    _UserQuotaMixin,
    _UserQuotaSetOnlyMixin,
)


class _MockNoDirectoryQuota(_UserQuotaMixin, _MockCore):
    """Mock backend that backs user quotas but no directory quotas at all."""


class _MockDirectorySetOnly(_DirectoryQuotaSetOnlyMixin, _UserQuotaMixin, _MockCore):
    """Lustre-shape directory quotas: set/delete but no enumeration (list)."""


class _MockNoUserQuota(_DirectoryQuotaMixin, _MockCore):
    """Mock backend that backs directory quotas but no user quotas at all."""


class _MockUserSetOnly(_DirectoryQuotaMixin, _UserQuotaSetOnlyMixin, _MockCore):
    """Lustre-shape user quotas: set/delete but no enumeration (list)."""


def _dir_quals(**kv: str) -> dict[str, dict[str, str]]:
    """Build directory-quota qualifier test data."""
    return {CAP_GROUP_DIRECTORY_QUOTA: dict(kv)}


def _user_quals(**kv: str) -> dict[str, dict[str, str]]:
    """Build user-quota qualifier test data."""
    return {CAP_GROUP_USER_QUOTA: dict(kv)}


class TestMockStorageApi:
    """Tests for MockStorageApi."""

    def test_health_check_passes_by_default(self) -> None:
        """Verify health check passes by default."""
        MockStorageApi().health_check()

    def test_health_check_raises_when_unhealthy(self) -> None:
        """Verify health check raises when unhealthy."""
        api = MockStorageApi(healthy=False)
        with pytest.raises(AuthenticationError):
            api.health_check()

    def test_create_volume_round_trip(self) -> None:
        """Verify create volume round trip."""
        api = MockStorageApi(tenant_id="t-1", hard_limit_bytes=10 * 1024**3)
        vol = api.create_volume(
            CreateVolumeRequest(
                size_bytes=1024**3,
                volume_type="file",
                name="probe-1",
                tags={"isvtest-run-id": "abc"},
            )
        )
        assert vol.tenant_id == "t-1"
        assert vol.id.startswith("vol-")
        assert vol.state == "available"
        assert vol.size_bytes == 1024**3
        assert vol.name == "probe-1"
        assert vol.tags == {"isvtest-run-id": "abc"}

        fetched = api.get_volume(GetVolumeRequest(volume_id=vol.id))
        assert fetched.id == vol.id

    def test_tenant_quota_reflects_provisioned_volumes(self) -> None:
        """Verify tenant quota reflects provisioned volumes."""
        api = MockStorageApi(tenant_id="t-1", hard_limit_bytes=10 * 1024**3)
        assert api.get_tenant_quota(GetTenantQuotaRequest()).used_bytes == 0

        api.create_volume(CreateVolumeRequest(size_bytes=2 * 1024**3, volume_type="block"))
        api.create_volume(CreateVolumeRequest(size_bytes=3 * 1024**3, volume_type="block"))
        quota = api.get_tenant_quota(GetTenantQuotaRequest())
        assert quota.tenant_id == "t-1"
        assert quota.hard_limit_bytes == 10 * 1024**3
        assert quota.used_bytes == 5 * 1024**3

    def test_list_tenant_quotas_returns_single_untiered_entry(self) -> None:
        """Verify list tenant quotas returns single untiered entry."""
        api = MockStorageApi(tenant_id="t-1", hard_limit_bytes=10 * 1024**3)
        resp = api.list_tenant_quotas(ListTenantQuotasRequest())
        assert len(resp.tenant_quotas) == 1
        only = resp.tenant_quotas[0]
        assert only.tenant_id == "t-1"
        assert only.tier is None

    def test_delete_volume_is_idempotent(self) -> None:
        """Verify delete volume is idempotent."""
        api = MockStorageApi()
        vol = api.create_volume(CreateVolumeRequest(size_bytes=1024, volume_type="file"))
        api.delete_volume(DeleteVolumeRequest(volume_id=vol.id))
        api.delete_volume(DeleteVolumeRequest(volume_id=vol.id))
        api.delete_volume(DeleteVolumeRequest(volume_id="never-existed"))

        with pytest.raises(NotFoundError):
            api.get_volume(GetVolumeRequest(volume_id=vol.id))

    def test_list_volumes_honors_ids_filter(self) -> None:
        """Verify list volumes honors ids filter."""
        api = MockStorageApi()
        v1 = api.create_volume(CreateVolumeRequest(size_bytes=1024, volume_type="file"))
        api.create_volume(CreateVolumeRequest(size_bytes=1024, volume_type="file"))
        result = api.list_volumes(ListVolumesRequest(ids=(v1.id,))).volumes
        assert [v.id for v in result] == [v1.id]

    def test_list_volumes_honors_tag_filters(self) -> None:
        """Verify list volumes honors tag filters."""
        api = MockStorageApi()
        api.create_volume(CreateVolumeRequest(size_bytes=1024, volume_type="file", tags={"env": "dev"}))
        v2 = api.create_volume(CreateVolumeRequest(size_bytes=1024, volume_type="file", tags={"env": "prod"}))

        result = api.list_volumes(ListVolumesRequest(tag_filters=(TagFilter("env", ("prod",)),))).volumes
        assert [v.id for v in result] == [v2.id]

        # Existence filter (empty values tuple) matches both.
        result = api.list_volumes(ListVolumesRequest(tag_filters=(TagFilter("env"),))).volumes
        assert len(result) == 2

        # Conjunction: missing key means no match.
        result = api.list_volumes(ListVolumesRequest(tag_filters=(TagFilter("missing-key"),))).volumes
        assert result == ()

    def test_quota_exceeded_raised_on_over_provision(self) -> None:
        """Verify quota exceeded raised on over provision."""
        api = MockStorageApi(hard_limit_bytes=1024)
        with pytest.raises(QuotaExceededError):
            api.create_volume(CreateVolumeRequest(size_bytes=2048, volume_type="file"))

    def test_unknown_tenant_raises_not_found(self) -> None:
        """Verify unknown tenant raises not found."""
        api = MockStorageApi(tenant_id="t-1")
        with pytest.raises(NotFoundError):
            api.get_tenant_quota(GetTenantQuotaRequest(tenant_id="t-other"))


@pytest.fixture(params=["backend", "caller"])
def directory_id_assignment(request: pytest.FixtureRequest) -> Literal["backend", "caller"]:
    """Parametrize directory-quota tests over both id-assignment modes."""
    return request.param


def _new_directory_quota(
    *,
    id_assignment: Literal["backend", "caller"],
    path: str = "projects/team-a",
    id: str = "q1",  # noqa: A002 -- matches DirectoryQuota.id field name
    hard: QuotaLimits | None = None,
) -> DirectoryQuota:
    """Build a ``DirectoryQuota`` populated correctly for the given id mode."""
    return DirectoryQuota(
        tenant_id="mock-tenant",
        volume_id="v1",
        path=path,
        id=id if id_assignment == "caller" else None,
        hard=hard,
    )


class TestMockDirectoryQuotas:
    """Round-trip the directory-quota surface across both id-assignment modes."""

    def test_set_get_list_delete_round_trip(self, directory_id_assignment: Literal["backend", "caller"]) -> None:
        """Verify set get list delete round trip."""
        api = MockStorageApi(qualifiers=_dir_quals(**{QUAL_ID_ASSIGNMENT: directory_id_assignment}))
        stored = api.set_directory_quota(
            SetDirectoryQuotaRequest(
                _new_directory_quota(
                    id_assignment=directory_id_assignment,
                    hard=QuotaLimits(bytes=1024, inodes=10),
                )
            )
        )

        if directory_id_assignment == "caller":
            assert stored.id == "q1"
        else:
            assert stored.id is not None
            assert stored.id.startswith("dq-")
        assert stored.path == "projects/team-a"
        assert stored.hard == QuotaLimits(bytes=1024, inodes=10)

        fetched_by_path = api.get_directory_quota(GetDirectoryQuotaRequest(volume_id="v1", path="projects/team-a"))
        assert fetched_by_path.id == stored.id

        fetched_by_id = api.get_directory_quota(GetDirectoryQuotaRequest(volume_id="v1", id=stored.id))
        assert fetched_by_id.path == "projects/team-a"

        listed = api.list_directory_quotas(ListDirectoryQuotasRequest(volume_id="v1")).directory_quotas
        assert [q.path for q in listed] == ["projects/team-a"]

        api.delete_directory_quota(DeleteDirectoryQuotaRequest(volume_id="v1", path="projects/team-a"))
        with pytest.raises(NotFoundError):
            api.get_directory_quota(GetDirectoryQuotaRequest(volume_id="v1", path="projects/team-a"))

    def test_set_caller_mode_requires_id(self) -> None:
        """Verify set caller mode requires id."""
        api = MockStorageApi(qualifiers=_dir_quals(**{QUAL_ID_ASSIGNMENT: "caller"}))
        with pytest.raises(ValidationError):
            api.set_directory_quota(
                SetDirectoryQuotaRequest(DirectoryQuota(tenant_id="mock-tenant", volume_id="v1", path="/a", id=None))
            )

    def test_set_backend_mode_requires_path(self) -> None:
        """Verify set backend mode requires path."""
        api = MockStorageApi(qualifiers=_dir_quals(**{QUAL_ID_ASSIGNMENT: "backend"}))
        with pytest.raises(ValidationError):
            api.set_directory_quota(
                SetDirectoryQuotaRequest(
                    DirectoryQuota(tenant_id="mock-tenant", volume_id="v1", path=None, id="forced")
                )
            )

    def test_set_backend_mode_reuses_id_on_update(self) -> None:
        """Verify set backend mode reuses id on update."""
        api = MockStorageApi(qualifiers=_dir_quals(**{QUAL_ID_ASSIGNMENT: "backend"}))
        first = api.set_directory_quota(
            SetDirectoryQuotaRequest(_new_directory_quota(id_assignment="backend", hard=QuotaLimits(bytes=1024)))
        )
        second = api.set_directory_quota(
            SetDirectoryQuotaRequest(_new_directory_quota(id_assignment="backend", hard=QuotaLimits(bytes=2048)))
        )
        assert first.id == second.id
        assert second.hard == QuotaLimits(bytes=2048)

    def test_byte_granularity_ceil_rounds(self, directory_id_assignment: Literal["backend", "caller"]) -> None:
        """Verify byte granularity ceil rounds."""
        api = MockStorageApi(
            qualifiers=_dir_quals(**{QUAL_ID_ASSIGNMENT: directory_id_assignment, QUAL_BYTE_GRANULARITY: "1024"})
        )
        stored = api.set_directory_quota(
            SetDirectoryQuotaRequest(
                _new_directory_quota(id_assignment=directory_id_assignment, hard=QuotaLimits(bytes=1500))
            )
        )
        assert stored.hard is not None
        assert stored.hard.bytes == 2048

    def test_inodes_unsupported_drops_inode_limit(self, directory_id_assignment: Literal["backend", "caller"]) -> None:
        """Verify inodes unsupported drops inode limit."""
        api = MockStorageApi(
            qualifiers=_dir_quals(**{QUAL_ID_ASSIGNMENT: directory_id_assignment, QUAL_INODES: "false"})
        )
        stored = api.set_directory_quota(
            SetDirectoryQuotaRequest(
                _new_directory_quota(id_assignment=directory_id_assignment, hard=QuotaLimits(bytes=1024, inodes=42))
            )
        )
        assert stored.hard == QuotaLimits(bytes=1024, inodes=None)

    def test_delete_missing_record_is_noop(self, directory_id_assignment: Literal["backend", "caller"]) -> None:
        """Verify delete missing record is noop."""
        api = MockStorageApi(qualifiers=_dir_quals(**{QUAL_ID_ASSIGNMENT: directory_id_assignment}))
        api.delete_directory_quota(DeleteDirectoryQuotaRequest(volume_id="v1", path="/never-set"))

    def test_delete_with_disagreeing_keys_raises_conflict(
        self, directory_id_assignment: Literal["backend", "caller"]
    ) -> None:
        """Verify delete with disagreeing keys raises conflict."""
        api = MockStorageApi(qualifiers=_dir_quals(**{QUAL_ID_ASSIGNMENT: directory_id_assignment}))
        stored = api.set_directory_quota(
            SetDirectoryQuotaRequest(_new_directory_quota(id_assignment=directory_id_assignment))
        )
        with pytest.raises(ConflictError):
            api.delete_directory_quota(
                DeleteDirectoryQuotaRequest(volume_id="v1", path=stored.path, id="never-existed")
            )

    def test_surface_absent_raises(self) -> None:
        # A backend without the directory-quota mixin leaves every
        # directory-quota call falling through to the base raise.
        """Verify surface absent raises."""
        api = _MockNoDirectoryQuota()
        with pytest.raises(NotSupportedError):
            api.list_directory_quotas(ListDirectoryQuotasRequest(volume_id="v1"))
        with pytest.raises(NotSupportedError):
            api.set_directory_quota(
                SetDirectoryQuotaRequest(DirectoryQuota(tenant_id="mock-tenant", volume_id="v1", path="/a"))
            )
        with pytest.raises(NotSupportedError):
            api.delete_directory_quota(DeleteDirectoryQuotaRequest(volume_id="v1", path="/a"))

    def test_list_unsupported_raises(self, directory_id_assignment: Literal["backend", "caller"]) -> None:
        # Lustre-shape: set/delete present, list absent.
        """Verify list unsupported raises."""
        api = _MockDirectorySetOnly(qualifiers=_dir_quals(**{QUAL_ID_ASSIGNMENT: directory_id_assignment}))
        with pytest.raises(NotSupportedError):
            api.list_directory_quotas(ListDirectoryQuotasRequest(volume_id="v1"))

    def test_multi_path_binding_rejected_at_construction(self) -> None:
        """Verify multi path binding rejected at construction."""
        with pytest.raises(NotImplementedError):
            MockStorageApi(qualifiers=_dir_quals(**{QUAL_MULTI_PATH_BINDING: "true"}))


class TestMockUserQuotas:
    """Round-trip the user-quota surface."""

    def test_set_get_list_delete_per_user(self) -> None:
        """Verify set get list delete per user."""
        api = MockStorageApi()
        stored = api.set_user_quota(
            SetUserQuotaRequest(
                UserQuota(tenant_id="mock-tenant", volume_id="v1", user="1001", hard=QuotaLimits(bytes=512, inodes=5))
            )
        )
        assert stored.user == "1001"
        assert stored.hard == QuotaLimits(bytes=512, inodes=5)

        fetched = api.get_user_quota(GetUserQuotaRequest(volume_id="v1", user="1001"))
        assert fetched.user == "1001"

        listed = api.list_user_quotas(ListUserQuotasRequest(volume_id="v1")).user_quotas
        assert [q.user for q in listed] == ["1001"]

        api.delete_user_quota(DeleteUserQuotaRequest(volume_id="v1", user="1001"))
        with pytest.raises(NotFoundError):
            api.get_user_quota(GetUserQuotaRequest(volume_id="v1", user="1001"))

    def test_default_user_slot_round_trip(self) -> None:
        """Verify default user slot round trip."""
        api = MockStorageApi()
        stored = api.set_user_quota(
            SetUserQuotaRequest(
                UserQuota(tenant_id="mock-tenant", volume_id="v1", user=None, hard=QuotaLimits(bytes=2048))
            )
        )
        assert stored.user is None
        fetched = api.get_user_quota(GetUserQuotaRequest(volume_id="v1", user=None))
        assert fetched.user is None
        api.delete_user_quota(DeleteUserQuotaRequest(volume_id="v1", user=None))
        with pytest.raises(NotFoundError):
            api.get_user_quota(GetUserQuotaRequest(volume_id="v1", user=None))

    def test_default_user_unsupported_raises(self) -> None:
        """Verify default user unsupported raises."""
        api = MockStorageApi(qualifiers=_user_quals(**{QUAL_DEFAULT_USER_SLOT: "false"}))
        with pytest.raises(NotSupportedError):
            api.set_user_quota(SetUserQuotaRequest(UserQuota(tenant_id="mock-tenant", volume_id="v1", user=None)))
        with pytest.raises(NotSupportedError):
            api.delete_user_quota(DeleteUserQuotaRequest(volume_id="v1", user=None))

    def test_surface_absent_raises(self) -> None:
        """Verify surface absent raises."""
        api = _MockNoUserQuota()
        with pytest.raises(NotSupportedError):
            api.list_user_quotas(ListUserQuotasRequest(volume_id="v1"))
        with pytest.raises(NotSupportedError):
            api.set_user_quota(SetUserQuotaRequest(UserQuota(tenant_id="mock-tenant", volume_id="v1", user="1001")))
        with pytest.raises(NotSupportedError):
            api.delete_user_quota(DeleteUserQuotaRequest(volume_id="v1", user="1001"))

    def test_byte_granularity_ceil_rounds(self) -> None:
        """Verify byte granularity ceil rounds."""
        api = MockStorageApi(qualifiers=_user_quals(**{QUAL_BYTE_GRANULARITY: "1024"}))
        stored = api.set_user_quota(
            SetUserQuotaRequest(
                UserQuota(tenant_id="mock-tenant", volume_id="v1", user="1001", hard=QuotaLimits(bytes=1500))
            )
        )
        assert stored.hard is not None
        assert stored.hard.bytes == 2048

    def test_inodes_unsupported_drops_inode_limit(self) -> None:
        """Verify inodes unsupported drops inode limit."""
        api = MockStorageApi(qualifiers=_user_quals(**{QUAL_INODES: "false"}))
        stored = api.set_user_quota(
            SetUserQuotaRequest(
                UserQuota(tenant_id="mock-tenant", volume_id="v1", user="1001", hard=QuotaLimits(bytes=1024, inodes=42))
            )
        )
        assert stored.hard == QuotaLimits(bytes=1024, inodes=None)

    def test_list_unsupported_raises(self) -> None:
        # Lustre-shape: set/delete present, list absent.
        """Verify list unsupported raises."""
        api = _MockUserSetOnly()
        with pytest.raises(NotSupportedError):
            api.list_user_quotas(ListUserQuotasRequest(volume_id="v1"))
