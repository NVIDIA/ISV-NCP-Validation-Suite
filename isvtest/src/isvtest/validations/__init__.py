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
from isvtest.validations.host import (
    CloudInitCheck,
    ContainerRuntimeCheck,
    CpuInfoCheck,
    DriverCheck,
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
    InstancePowerCycleCheck,
    InstanceRebootCheck,
    InstanceStartCheck,
    InstanceStateCheck,
    InstanceStopCheck,
    InstanceTagCheck,
    StableIdentifierCheck,
)
from isvtest.validations.k8s_conformance import (
    K8sCncfConformanceCheck,
)
from isvtest.validations.network import (
    ByoipCheck,
    DhcpIpManagementCheck,
    FloatingIpCheck,
    LocalizedDnsCheck,
    NetworkConnectivityCheck,
    NetworkProvisionedCheck,
    SecurityBlockingCheck,
    SgCrudCheck,
    StablePrivateIpCheck,
    SubnetConfigCheck,
    TrafficFlowCheck,
    VpcCrudCheck,
    VpcIpConfigCheck,
    VpcIsolationCheck,
    VpcPeeringCheck,
)
from isvtest.validations.nim import (
    NimHealthCheck,
    NimInferenceCheck,
    NimModelCheck,
)

__all__ = [
    "AccessKeyAuthenticatedCheck",
    "AccessKeyCreatedCheck",
    "AccessKeyDisabledCheck",
    "AccessKeyRejectedCheck",
    "ByoipCheck",
    "CloudInitCheck",
    "ClusterHealthCheck",
    "ContainerRuntimeCheck",
    "CpuInfoCheck",
    "DhcpIpManagementCheck",
    "DriverCheck",
    "FieldExistsCheck",
    "FieldValueCheck",
    "FloatingIpCheck",
    "GpuOperatorInstalledCheck",
    "InstanceCreatedCheck",
    "InstanceListCheck",
    "InstancePowerCycleCheck",
    "InstanceRebootCheck",
    "InstanceStartCheck",
    "InstanceStateCheck",
    "InstanceStopCheck",
    "InstanceTagCheck",
    "K8sCncfConformanceCheck",
    "LocalizedDnsCheck",
    "NetworkConnectivityCheck",
    "NetworkProvisionedCheck",
    "NimHealthCheck",
    "NimInferenceCheck",
    "NimModelCheck",
    "NodeCountCheck",
    "PerformanceCheck",
    "SchemaValidation",
    "SecurityBlockingCheck",
    "SgCrudCheck",
    "StableIdentifierCheck",
    "StablePrivateIpCheck",
    "StepSuccessCheck",
    "SubnetConfigCheck",
    "TenantCreatedCheck",
    "TenantInfoCheck",
    "TenantListedCheck",
    "TrafficFlowCheck",
    "VpcCrudCheck",
    "VpcIpConfigCheck",
    "VpcIsolationCheck",
    "VpcPeeringCheck",
]
