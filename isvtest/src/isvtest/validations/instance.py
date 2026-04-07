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
from isvtest.validations.generic import check_operations_passed


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
    markers: ClassVar[list[str]] = ["vm", "bare_metal"]

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
    markers: ClassVar[list[str]] = ["vm", "bare_metal"]

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


class InstancePowerCycleCheck(BaseValidation):
    """Validate that an instance was power-cycled successfully.

    A power-cycle is a hard power off followed by power on (cold start),
    unlike a reboot which is an OS-level restart. This validates that the
    node recovers from complete power loss.

    Checks the power-cycle step output for:
    - power_cycle_initiated: True (power-off API call succeeded)
    - power_was_off: True (node actually reached powered-off state)
    - state: "running" (node recovered)
    - ssh_ready: True (SSH connectivity restored)
    - recovery_seconds: Within max_recovery_time

    Config:
        step_output: The power-cycle step output to check
        max_recovery_time: Maximum seconds from power-on to SSH ready (default: 900)

    Step output (from power_cycle_instance.py):
        instance_id: Instance identifier
        power_cycle_initiated: Whether power-off API call succeeded
        power_was_off: Whether node reached powered-off state
        state: Instance state after recovery
        ssh_ready: Whether SSH is accessible after recovery
        recovery_seconds: Seconds from power-on to SSH ready
    """

    description: ClassVar[str] = "Check instance recovered from power-cycle"
    markers: ClassVar[list[str]] = ["bare_metal"]

    def run(self) -> None:
        step_output = self.config.get("step_output", {})
        max_recovery_time = self.config.get("max_recovery_time", 900)

        instance_id = step_output.get("instance_id")
        if not instance_id:
            self.set_failed("No 'instance_id' in step output")
            return

        power_cycle_initiated = step_output.get("power_cycle_initiated", False)
        if not power_cycle_initiated:
            self.set_failed(f"Power-cycle was not initiated for {instance_id}")
            return

        power_was_off = step_output.get("power_was_off", False)
        if not power_was_off:
            self.set_failed(f"Instance {instance_id} did not reach powered-off state")
            return

        state = step_output.get("state")
        if state != "running":
            self.set_failed(f"Instance {instance_id} not running after power-cycle: {state}")
            return

        ssh_ready = step_output.get("ssh_ready", False)
        if not ssh_ready:
            self.set_failed(f"SSH not ready after power-cycle for {instance_id}")
            return

        recovery = step_output.get("recovery_seconds")
        if recovery is not None and recovery > max_recovery_time:
            self.set_failed(f"Instance {instance_id} recovery took {recovery}s > {max_recovery_time}s")
            return

        recovery_str = f", recovery={recovery}s" if recovery is not None else ""
        self.set_passed(f"Instance {instance_id} recovered from power-cycle (state={state}{recovery_str})")


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


class InstanceStopCheck(BaseValidation):
    """Validate that an instance was stopped successfully (not destroyed).

    Checks the stop step output for:
    - stop_initiated: True (API call succeeded)
    - state: "stopped" (instance reached stopped state)

    Config:
        step_output: The stop step output to check

    Step output (from stop_instance.py):
        instance_id: Instance identifier
        stop_initiated: Whether stop API call succeeded
        state: Instance state after stop
    """

    description: ClassVar[str] = "Check instance stopped successfully without being destroyed"
    markers: ClassVar[list[str]] = ["vm", "bare_metal"]

    def run(self) -> None:
        step_output = self.config.get("step_output", {})

        instance_id = step_output.get("instance_id")
        if not instance_id:
            self.set_failed("No 'instance_id' in step output")
            return

        stop_initiated = step_output.get("stop_initiated", False)
        if not stop_initiated:
            self.set_failed(f"Stop was not initiated for {instance_id}")
            return

        state = step_output.get("state")
        if state != "stopped":
            self.set_failed(f"Instance {instance_id} state: expected stopped, got {state}")
            return

        self.set_passed(f"Instance {instance_id} stopped successfully (state={state})")


class InstanceStartCheck(BaseValidation):
    """Validate that a stopped instance was started successfully.

    Checks the start step output for:
    - start_initiated: True (API call succeeded)
    - state: "running" (instance recovered)
    - ssh_ready: True (SSH connectivity restored)

    Config:
        step_output: The start step output to check

    Step output (from start_instance.py):
        instance_id: Instance identifier
        start_initiated: Whether start API call succeeded
        state: Instance state after start
        ssh_ready: Whether SSH is accessible after start
    """

    description: ClassVar[str] = "Check stopped instance started successfully"
    markers: ClassVar[list[str]] = ["vm", "bare_metal"]

    def run(self) -> None:
        step_output = self.config.get("step_output", {})

        instance_id = step_output.get("instance_id")
        if not instance_id:
            self.set_failed("No 'instance_id' in step output")
            return

        start_initiated = step_output.get("start_initiated", False)
        if not start_initiated:
            self.set_failed(f"Start was not initiated for {instance_id}")
            return

        state = step_output.get("state")
        if state != "running":
            self.set_failed(f"Instance {instance_id} not running after start: {state}")
            return

        ssh_ready = step_output.get("ssh_ready", False)
        if not ssh_ready:
            self.set_failed(f"SSH not ready after start for {instance_id}")
            return

        self.set_passed(f"Instance {instance_id} started successfully (state={state})")


class InstanceTagCheck(BaseValidation):
    """Validate that user-defined tags are present on an instance.

    Config:
        step_output: The describe_tags step output
        required_keys: List of tag keys that must be present (default: [])

    Step output:
        instance_id: Instance identifier
        tags: Dict of tag key→value pairs
        tag_count: Number of tags
    """

    description: ClassVar[str] = "Check instance tags are present"
    markers: ClassVar[list[str]] = ["vm"]

    def run(self) -> None:
        step_output = self.config.get("step_output", {})
        required_keys = self.config.get("required_keys", [])

        instance_id = step_output.get("instance_id")
        if not instance_id:
            self.set_failed("No 'instance_id' in step output")
            return

        tags = step_output.get("tags")
        if tags is None:
            self.set_failed(f"No 'tags' in step output for {instance_id}")
            return

        if not tags:
            self.set_failed(f"Instance {instance_id} has no tags")
            return

        missing = [k for k in required_keys if k not in tags]
        if missing:
            self.set_failed(f"Instance {instance_id} missing required tags: {missing}")
            return

        tag_count = step_output.get("tag_count", len(tags))
        self.set_passed(f"Instance {instance_id} has {tag_count} tag(s): {list(tags.keys())}")


class SerialConsoleCheck(BaseValidation):
    """Validate serial console access for an instance (read-only).

    Passes if serial console access is enabled at the account level OR
    console output was successfully retrieved. Nitro-based instances
    often return empty console output but still support serial console
    access via EC2 Instance Connect.

    Config:
        step_output: The serial_console step output

    Step output:
        instance_id: Instance identifier
        console_available: Whether console output was retrieved
        serial_access_enabled: Whether serial console access is enabled at account level
        output_length: Length of console output in characters
    """

    description: ClassVar[str] = "Check serial console access"
    markers: ClassVar[list[str]] = ["vm", "bare_metal"]

    def run(self) -> None:
        step_output = self.config.get("step_output", {})

        instance_id = step_output.get("instance_id")
        if not instance_id:
            self.set_failed("No 'instance_id' in step output")
            return

        console_available = step_output.get("console_available", False)
        serial_access = step_output.get("serial_access_enabled", False)
        output_length = step_output.get("output_length", 0)

        if not console_available and not serial_access:
            error = step_output.get("error", "no console output and serial access not enabled")
            self.set_failed(f"Serial console not accessible for {instance_id}: {error}")
            return

        details = []
        if serial_access:
            details.append("serial access enabled")
        if console_available:
            details.append(f"{output_length} chars of output")
        else:
            details.append("no output (Nitro instance)")
            self.log.warning(
                f"Serial access enabled but no console output for {instance_id} "
                f"— expected on Nitro instances, but verify if this is not a Nitro instance"
            )

        self.set_passed(f"Serial console available for {instance_id} ({', '.join(details)})")


class TopologyPlacementCheck(BaseValidation):
    """Validate topology-based placement support for an instance.

    Checks that the platform supports placement groups (or equivalent
    topology-aware scheduling) and that all placement operations passed.
    Delegates operations checking to ``CrudOperationsCheck``.

    Config:
        step_output: The topology_placement step output

    Step output:
        placement_supported: Whether placement groups are supported
        availability_zone: Instance availability zone
        placement_group: Name of the test placement group
        placement_strategy: Placement strategy (e.g., cluster)
        operations: Dict of operation results
    """

    description: ClassVar[str] = "Check topology-based placement support"
    markers: ClassVar[list[str]] = ["bare_metal"]

    def run(self) -> None:
        step_output = self.config.get("step_output", {})

        instance_id = step_output.get("instance_id")
        if not instance_id:
            self.set_failed("No 'instance_id' in step output")
            return

        placement_supported = step_output.get("placement_supported", False)
        az = step_output.get("availability_zone", "")
        strategy = step_output.get("placement_strategy", "")

        if not placement_supported:
            error = step_output.get("error", "placement not supported")
            self.set_failed(f"Topology placement not supported for {instance_id}: {error}")
            return

        ops = step_output.get("operations", {})
        _, failed = check_operations_passed(ops)
        if failed:
            self.set_failed(f"Placement operations failed: {', '.join(failed)}")
            return

        details = [f"AZ={az}", f"strategy={strategy}"]
        self.set_passed(f"Topology placement supported for {instance_id} ({', '.join(details)})")


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
    markers: ClassVar[list[str]] = ["vm", "bare_metal"]

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
