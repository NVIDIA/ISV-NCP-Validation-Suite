# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Slurm job submission validations."""

from typing import ClassVar

from isvtest.core.nvidia import count_gpus_from_list_output, has_gpu_output
from isvtest.core.validation import BaseValidation


class SlurmJobSubmission(BaseValidation):
    """Test basic Slurm job submission and completion."""

    description: ClassVar[str] = "Verify Slurm job submission works with GPU access"
    timeout: ClassVar[int] = 60
    markers: ClassVar[list[str]] = ["slurm"]

    def run(self) -> None:
        # Submit a simple job that lists GPUs
        result = self.run_command("srun --partition=gpu --gres=gpu:1 nvidia-smi -L")

        if result.exit_code != 0:
            self.set_failed(f"srun job failed: {result.stderr}")
            return

        if not result.stdout.strip():
            self.set_failed("No output from nvidia-smi")
            return

        if not has_gpu_output(result.stdout):
            self.set_failed("GPU not found in nvidia-smi output")
            return

        # Count GPUs found using shared parser
        gpu_count = count_gpus_from_list_output(result.stdout)
        self.set_passed(f"Job submission successful, found {gpu_count} GPU(s)")
