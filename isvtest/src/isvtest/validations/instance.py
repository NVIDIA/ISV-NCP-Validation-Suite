# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Instance/VM validations for step outputs.

Validations for EC2 instances, virtual machines, and compute resources.
"""

from typing import ClassVar

from isvtest.core.validation import BaseValidation


class InstanceStateCheck(BaseValidation):
    """Validate instance state.

    Config:
        step_output: The step output to check
        expected_state: Expected state (default: "running")

    Step output:
        state: Instance state
        instance_id: Instance identifier
    """

    description: ClassVar[str] = "Check instance is in expected state"
    markers: ClassVar[list[str]] = ["vm"]

    def run(self) -> None:
        step_output = self.config.get("step_output", {})
        expected_state = self.config.get("expected_state", "running")

        instance_id = step_output.get("instance_id")
        actual_state = step_output.get("state")

        if not instance_id:
            self.set_failed("No 'instance_id' in step output")
            return

        if not actual_state:
            self.set_failed(f"No 'state' for instance {instance_id}")
            return

        if actual_state == expected_state:
            self.set_passed(f"Instance {instance_id} is {actual_state}")
        else:
            self.set_failed(f"Instance {instance_id} state: expected {expected_state}, got {actual_state}")


class InstanceRebootCheck(BaseValidation):
    """Validate that an instance was rebooted successfully.

    Checks the reboot step output for:
    - reboot_initiated: True (API call succeeded)
    - state: "running" (instance recovered)
    - ssh_ready: True (SSH connectivity restored)
    - uptime_seconds: Low value (proves reboot actually occurred)

    Config:
        step_output: The reboot step output to check
        max_uptime: Maximum uptime in seconds to consider reboot confirmed (default: 600)

    Step output (from reboot_instance.py):
        instance_id: Instance identifier
        reboot_initiated: Whether reboot API call succeeded
        state: Instance state after reboot
        ssh_ready: Whether SSH is accessible after reboot
        uptime_seconds: System uptime after reboot
        reboot_confirmed: Whether uptime comparison confirms reboot
    """

    description: ClassVar[str] = "Check instance rebooted successfully"
    markers: ClassVar[list[str]] = ["vm"]

    def run(self) -> None:
        step_output = self.config.get("step_output", {})
        max_uptime = self.config.get("max_uptime", 600)

        instance_id = step_output.get("instance_id")
        if not instance_id:
            self.set_failed("No 'instance_id' in step output")
            return

        # Check reboot was initiated
        reboot_initiated = step_output.get("reboot_initiated", False)
        if not reboot_initiated:
            self.set_failed(f"Reboot was not initiated for {instance_id}")
            return

        # Check instance state after reboot
        state = step_output.get("state")
        if state != "running":
            self.set_failed(f"Instance {instance_id} not running after reboot: {state}")
            return

        # Check SSH connectivity restored
        ssh_ready = step_output.get("ssh_ready", False)
        if not ssh_ready:
            self.set_failed(f"SSH not ready after reboot for {instance_id}")
            return

        # Check uptime to confirm reboot actually happened
        uptime = step_output.get("uptime_seconds")
        reboot_confirmed = step_output.get("reboot_confirmed")

        if uptime is not None and uptime > max_uptime:
            self.set_failed(
                f"Instance {instance_id} uptime {uptime:.0f}s > {max_uptime}s, reboot may not have occurred"
            )
            return

        if reboot_confirmed is False:
            self.set_failed(f"Instance {instance_id} reboot not confirmed by uptime comparison")
            return

        uptime_str = f", uptime={uptime:.0f}s" if uptime is not None else ""
        self.set_passed(f"Instance {instance_id} rebooted successfully (state={state}{uptime_str})")


class InstanceCreatedCheck(BaseValidation):
    """Validate instance was created successfully.

    Config:
        step_output: The step output to check

    Step output:
        instance_id: Instance identifier
        public_ip: Optional public IP
        private_ip: Optional private IP
    """

    description: ClassVar[str] = "Check instance was created"
    markers: ClassVar[list[str]] = ["vm"]

    def run(self) -> None:
        step_output = self.config.get("step_output", {})

        instance_id = step_output.get("instance_id")
        if not instance_id:
            self.set_failed("No 'instance_id' in step output")
            return

        public_ip = step_output.get("public_ip", "N/A")
        private_ip = step_output.get("private_ip", "N/A")
        instance_type = step_output.get("instance_type", "unknown")

        self.set_passed(
            f"Instance {instance_id} created: type={instance_type}, public={public_ip}, private={private_ip}"
        )


class InstanceListCheck(BaseValidation):
    """Validate instance list from a VPC.

    Checks that the instances list exists, is non-empty (or meets min_count),
    validates required fields on each instance, and optionally verifies that
    a target instance appears in the list.

    Config:
        step_output: The step output to check
        min_count: Minimum number of instances expected (default: 1)

    Step output:
        instances: List of instance dicts
        count: Number of instances
        found_target: Whether target instance was found
        target_instance: Target instance ID searched for
    """

    description: ClassVar[str] = "Check instance list from VPC"
    markers: ClassVar[list[str]] = ["vm"]

    REQUIRED_FIELDS = ("instance_id", "state", "vpc_id")

    def run(self) -> None:
        step_output = self.config.get("step_output", {})
        min_count = self.config.get("min_count", 1)

        instances = step_output.get("instances")
        if instances is None:
            self.set_failed("No 'instances' key in step output")
            return

        if len(instances) < min_count:
            self.set_failed(f"Expected at least {min_count} instance(s), got {len(instances)}")
            return

        # Validate required fields on each instance
        for i, inst in enumerate(instances):
            for field in self.REQUIRED_FIELDS:
                if not inst.get(field):
                    self.set_failed(f"Instance at index {i} missing required field '{field}'")
                    return

        # Check target instance if specified
        found_target = step_output.get("found_target")
        target = step_output.get("target_instance")

        if found_target is not None and target:
            if not found_target:
                self.set_failed(f"Target instance '{target}' not found in list")
                return

        count = step_output.get("count", len(instances))
        msg = f"Listed {count} instance(s)"
        if target and found_target:
            msg += f", target '{target}' found"
        self.set_passed(msg)
