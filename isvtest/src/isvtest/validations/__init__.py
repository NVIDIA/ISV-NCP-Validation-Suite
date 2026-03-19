# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Validation classes for isvtest.

Validations are organized by category:
- generic: Field checks, schema validation, teardown/workload success
- cluster: Kubernetes cluster validations
- instance: VM/EC2 instance validations
- network: VPC, subnet, security group validations
- iam: Access key and tenant validations

All validations are also available via step_assertions for backward compatibility.
"""

from isvtest.validations.cluster import (
    ClusterHealthCheck,
    GpuOperatorInstalledCheck,
    NodeCountCheck,
    PerformanceCheck,
)
from isvtest.validations.generic import (
    FieldExistsCheck,
    FieldValueCheck,
    SchemaValidation,
    StepSuccessCheck,
)
from isvtest.validations.iam import (
    AccessKeyAuthenticatedCheck,
    AccessKeyCreatedCheck,
    AccessKeyDisabledCheck,
    AccessKeyRejectedCheck,
    TenantCreatedCheck,
    TenantInfoCheck,
    TenantListedCheck,
)
from isvtest.validations.instance import (
    InstanceCreatedCheck,
    InstanceListCheck,
    InstanceStateCheck,
)
from isvtest.validations.network import (
    DhcpIpManagementCheck,
    NetworkConnectivityCheck,
    NetworkProvisionedCheck,
    SecurityBlockingCheck,
    SubnetConfigCheck,
    TrafficFlowCheck,
    VpcCrudCheck,
    VpcIpConfigCheck,
    VpcIsolationCheck,
)
from isvtest.validations.nim import (
    SshNimHealthCheck,
    SshNimInferenceCheck,
    SshNimModelCheck,
)

__all__ = [
    "AccessKeyAuthenticatedCheck",
    "AccessKeyCreatedCheck",
    "AccessKeyDisabledCheck",
    "AccessKeyRejectedCheck",
    "ClusterHealthCheck",
    "DhcpIpManagementCheck",
    "FieldExistsCheck",
    "FieldValueCheck",
    "GpuOperatorInstalledCheck",
    "InstanceCreatedCheck",
    "InstanceListCheck",
    "InstanceStateCheck",
    "NetworkConnectivityCheck",
    "NetworkProvisionedCheck",
    "NodeCountCheck",
    "PerformanceCheck",
    "SchemaValidation",
    "SecurityBlockingCheck",
    "SshNimHealthCheck",
    "SshNimInferenceCheck",
    "SshNimModelCheck",
    "StepSuccessCheck",
    "SubnetConfigCheck",
    "TenantCreatedCheck",
    "TenantInfoCheck",
    "TenantListedCheck",
    "TrafficFlowCheck",
    "VpcCrudCheck",
    "VpcIpConfigCheck",
    "VpcIsolationCheck",
]
