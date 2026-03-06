# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Generic CRUD operations for all Carbide API resources.

Provides create/get/list/delete for every resource type that carbidecli
supports. Stubs should use these instead of calling run_carbide directly
for standard CRUD operations.

Usage:
    from common.resources import CarbideResource

    vpc = CarbideResource("vpc")
    result = vpc.create(name="my-vpc", site_id="...")
    vpc.get(result["id"])
    vpc.list()
    vpc.delete(result["id"])
"""

from typing import Any

from .carbide import run_carbide


class CarbideResource:
    """Generic CRUD wrapper for a Carbide API resource.

    Args:
        resource_type: The carbidecli resource name (e.g., "vpc", "subnet",
            "operating-system", "ssh-key-group")
    """

    def __init__(self, resource_type: str) -> None:
        self.resource_type = resource_type

    def create(self, **kwargs: str) -> dict[str, Any]:
        """Create a resource. Kwargs are passed as --key value args."""
        args = [self.resource_type, "create"]
        for key, value in kwargs.items():
            if value:
                args.extend([f"--{key.replace('_', '-')}", value])
        return run_carbide(*args)

    def get(self, resource_id: str) -> dict[str, Any]:
        """Get a resource by ID."""
        return run_carbide(self.resource_type, "get", resource_id)

    def list(self, **kwargs: str) -> list[dict[str, Any]] | dict[str, Any]:
        """List resources. Kwargs are passed as filter args."""
        args = [self.resource_type, "list"]
        for key, value in kwargs.items():
            if value:
                args.extend([f"--{key.replace('_', '-')}", value])
        result = run_carbide(*args)
        return result if isinstance(result, list) else result

    def delete(self, resource_id: str) -> bool:
        """Delete a resource by ID. Returns True on success or already-deleted."""
        try:
            run_carbide(self.resource_type, "delete", resource_id)
            return True
        except RuntimeError as e:
            if "not found" in str(e).lower() or "404" in str(e):
                return True
            raise

    def update(self, resource_id: str, **kwargs: str) -> dict[str, Any]:
        """Update a resource. Kwargs are passed as --key value args."""
        args = [self.resource_type, "update", resource_id]
        for key, value in kwargs.items():
            if value:
                args.extend([f"--{key.replace('_', '-')}", value])
        return run_carbide(*args)


# Pre-configured resource instances for all Carbide API resources.
# Names match the carbidecli subcommand names.

# Core infrastructure
site = CarbideResource("site")
vpc = CarbideResource("vpc")
vpc_prefix = CarbideResource("vpc-prefix")
subnet = CarbideResource("subnet")
nsg = CarbideResource("network-security-group")
ipblock = CarbideResource("ipblock")
allocation = CarbideResource("allocation")

# Compute
instance = CarbideResource("instance")
instance_type = CarbideResource("instance-type")
machine = CarbideResource("machine")
expected_machine = CarbideResource("expected-machine")
operating_system = CarbideResource("operating-system")

# Networking / fabric
infiniband_partition = CarbideResource("infiniband-partition")
nvlink_logical_partition = CarbideResource("nvlink-logical-partition")
nvlink_interface = CarbideResource("nvlink-interface")
dpu_extension_service = CarbideResource("dpu-extension-service")

# Identity / access
ssh_key_group = CarbideResource("sshkeygroup")
ssh_key = CarbideResource("sshkey")
tenant = CarbideResource("tenant")

# Hardware topology
rack = CarbideResource("rack")
tray = CarbideResource("tray")
sku = CarbideResource("sku")

# Observability
audit = CarbideResource("audit")
