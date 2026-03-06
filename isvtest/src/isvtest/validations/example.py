# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

from typing import ClassVar

from isvtest.core.validation import BaseValidation


class ExampleCheck(BaseValidation):
    """Example check demonstrating the BaseValidation pattern."""

    description = "An example check that verifies echo works."
    markers: ClassVar[list[str]] = []

    def run(self) -> None:
        result = self.run_command("echo 'hello world'")

        if result.exit_code != 0:
            self.set_failed(f"Command failed with exit code {result.exit_code}")
            return

        if "hello world" not in result.stdout:
            self.set_failed(f"Unexpected output: {result.stdout}")
            return

        self.set_passed("Echo command worked as expected")


class SecondExampleCheck(BaseValidation):
    """Second example check demonstrating the BaseValidation pattern."""

    description = "An example check that verifies echo works."
    markers: ClassVar[list[str]] = []

    def run(self) -> None:
        result = self.run_command("echo 'another example'")

        if result.exit_code != 0:
            self.set_failed(f"Command failed with exit code {result.exit_code}")
            return

        if "another example" not in result.stdout:
            self.set_failed(f"Unexpected output: {result.stdout}")
            return

        self.set_passed("Echo command worked as expected")
