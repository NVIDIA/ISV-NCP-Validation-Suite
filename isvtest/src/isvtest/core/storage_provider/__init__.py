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

"""Storage provider shim.

Python ABC + error taxonomy + value types that providers subclass once per
backend storage provider. The surface covers backend identity and capability
discovery (``properties``), authenticated health checks, tenant + volume
enumeration, and directory- and user-quota CRUD.

A shim subclasses ``Implementation``, overriding only the surfaces it backs; the
SDK *detects* which surfaces are supported and gates the rest. Support is also
declared in the provider manifest (the contract) and verified at runtime: the
validation suite probes every declared-``supported`` surface and fails if the
shim raises ``NotSupportedError`` / ``NotImplementedError``. Detection and the
manifest must agree. ``properties().capabilities()`` reports the composed states
+ L2 qualifiers per surface.

For orientation, quickstart, and source links see ``README.md``
co-located with this package. The per-method contract (inputs, outputs,
error conditions, capability/qualifier semantics) lives as docstrings on
the classes and methods in ``api.py``; the provider manifest schema is
``isvctl/schemas/storage-provider-manifest.schema.json``.

One authoring model (mirrors nv-storage): override only the served surfaces on an
``Implementation`` and compose it with ``new_implementation()``::

    # api.py - the file the provider ships per backend
    from isvtest.core.storage_provider import (
        Implementation, ProviderProperties, StorageProvider, new_implementation,
    )

    class MyStorageApi(Implementation):
        def health_check(self) -> None: ...
        def get_tenant_quota(self, req): ...
        def list_volumes(self, req): ...

    def build_api() -> StorageProvider:  # the one entry point the loader calls
        return new_implementation(core=_CORE, impl=MyStorageApi(), default_tenant="...")
"""

from isvtest.core.storage_provider.api import (
    API_VERSION,
    CAP_DIRECTORY_QUOTA_DELETE,
    CAP_DIRECTORY_QUOTA_GET,
    CAP_DIRECTORY_QUOTA_LIST,
    CAP_DIRECTORY_QUOTA_SET,
    CAP_GROUP_DIRECTORY_QUOTA,
    CAP_GROUP_QUOTA,
    CAP_GROUP_TENANT,
    CAP_GROUP_USER_QUOTA,
    CAP_GROUP_VOLUME,
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
    DEFAULT_INSTANCE_ID,
    QUAL_ACCOUNTING,
    QUAL_BYTE_GRANULARITY,
    QUAL_DEFAULT_USER_SLOT,
    QUAL_ID_ASSIGNMENT,
    QUAL_INODES,
    QUAL_MULTI_PATH_BINDING,
    QUAL_MULTI_TENANT,
    QUAL_TIERED,
    AuthenticationError,
    Capability,
    CapabilityState,
    ConflictError,
    CreateVolumeRequest,
    CsiSpec,
    DeleteDirectoryQuotaRequest,
    DeleteUserQuotaRequest,
    DeleteVolumeRequest,
    DirectoryQuota,
    GetDirectoryQuotaRequest,
    GetTenantQuotaRequest,
    GetTenantRequest,
    GetUserQuotaRequest,
    GetVolumeRequest,
    IDAssignment,
    Implementation,
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
    MountSpec,
    NotFoundError,
    NotSupportedError,
    ProviderProperties,
    QuotaAccounting,
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
    VolumeState,
    VolumeType,
    instance_or_default,
    new_implementation,
    with_default_tenant,
)
from isvtest.core.storage_provider.capabilities import (
    Capabilities,
    ImplementationCapabilities,
)
from isvtest.core.storage_provider.loader import (
    ShimLoadError,
    build_api_from_path,
)
from isvtest.core.storage_provider.mock import MockStorageApi

__all__ = [
    "API_VERSION",
    "CAPABILITY_IDS",
    "CAP_DIRECTORY_QUOTA_DELETE",
    "CAP_DIRECTORY_QUOTA_GET",
    "CAP_DIRECTORY_QUOTA_LIST",
    "CAP_DIRECTORY_QUOTA_SET",
    "CAP_GROUP_DIRECTORY_QUOTA",
    "CAP_GROUP_QUOTA",
    "CAP_GROUP_TENANT",
    "CAP_GROUP_USER_QUOTA",
    "CAP_GROUP_VOLUME",
    "CAP_TENANT_GET",
    "CAP_TENANT_GET_QUOTA",
    "CAP_TENANT_LIST",
    "CAP_TENANT_LIST_QUOTAS",
    "CAP_USER_QUOTA_DELETE",
    "CAP_USER_QUOTA_GET",
    "CAP_USER_QUOTA_LIST",
    "CAP_USER_QUOTA_SET",
    "CAP_VOLUME_CREATE",
    "CAP_VOLUME_DELETE",
    "CAP_VOLUME_GET",
    "CAP_VOLUME_LIST",
    "DEFAULT_INSTANCE_ID",
    "QUAL_ACCOUNTING",
    "QUAL_BYTE_GRANULARITY",
    "QUAL_DEFAULT_USER_SLOT",
    "QUAL_ID_ASSIGNMENT",
    "QUAL_INODES",
    "QUAL_MULTI_PATH_BINDING",
    "QUAL_MULTI_TENANT",
    "QUAL_TIERED",
    "AuthenticationError",
    "Capabilities",
    "Capability",
    "CapabilityState",
    "ConflictError",
    "CreateVolumeRequest",
    "CsiSpec",
    "DeleteDirectoryQuotaRequest",
    "DeleteUserQuotaRequest",
    "DeleteVolumeRequest",
    "DirectoryQuota",
    "GetDirectoryQuotaRequest",
    "GetTenantQuotaRequest",
    "GetTenantRequest",
    "GetUserQuotaRequest",
    "GetVolumeRequest",
    "IDAssignment",
    "Implementation",
    "ImplementationCapabilities",
    "ListDirectoryQuotasRequest",
    "ListDirectoryQuotasResponse",
    "ListTenantQuotasRequest",
    "ListTenantQuotasResponse",
    "ListTenantsRequest",
    "ListTenantsResponse",
    "ListUserQuotasRequest",
    "ListUserQuotasResponse",
    "ListVolumesRequest",
    "ListVolumesResponse",
    "MockStorageApi",
    "MountSpec",
    "NotFoundError",
    "NotSupportedError",
    "ProviderProperties",
    "QuotaAccounting",
    "QuotaExceededError",
    "QuotaLimits",
    "QuotaUsage",
    "SetDirectoryQuotaRequest",
    "SetUserQuotaRequest",
    "ShimLoadError",
    "StorageApiError",
    "StorageProvider",
    "TagFilter",
    "Tenant",
    "TenantQuota",
    "UnavailableError",
    "UserQuota",
    "ValidationError",
    "VersionMetadata",
    "Volume",
    "VolumeState",
    "VolumeType",
    "build_api_from_path",
    "instance_or_default",
    "new_implementation",
    "with_default_tenant",
]
