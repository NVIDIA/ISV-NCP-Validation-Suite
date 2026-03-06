# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Bare metal CUDA validations."""

from typing import ClassVar

from isvtest.core.nvidia import compare_versions, parse_cuda_version
from isvtest.core.validation import BaseValidation


class BmCudaVersion(BaseValidation):
    """Verify CUDA version is reported by nvidia-smi."""

    description: ClassVar[str] = "Query CUDA version from nvidia-smi (driver-reported max CUDA version)"
    timeout: ClassVar[int] = 30
    markers: ClassVar[list[str]] = ["bare_metal"]

    def run(self) -> None:
        result = self.run_command("nvidia-smi")

        if result.exit_code != 0:
            self.set_failed(f"nvidia-smi failed: {result.stderr}")
            return

        # Parse CUDA version using shared parser
        cuda_version = parse_cuda_version(result.stdout)

        if not cuda_version:
            self.set_failed("CUDA version not found in nvidia-smi output")
            return

        # Check against minimum version if configured
        min_version = self.config.get("min_version")
        if min_version:
            if not compare_versions(cuda_version, min_version):
                self.set_failed(f"CUDA version {cuda_version} is below minimum required {min_version}")
                return

        self.set_passed(f"CUDA version: {cuda_version}")
