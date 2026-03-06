# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""ISV workload validations.

This module contains longer-running workload tests that deploy real workloads
to validate GPU functionality and performance.
"""

from isvtest.workloads.k8s_nccl import K8sNcclWorkload
from isvtest.workloads.k8s_nim import K8sNimInferenceWorkload
from isvtest.workloads.k8s_nim_helm import K8sNimHelmWorkload
from isvtest.workloads.k8s_stress import K8sGpuStressWorkload
from isvtest.workloads.slurm_gpu_stress import SlurmGpuStressWorkload
from isvtest.workloads.slurm_nccl_multinode import SlurmNcclMultiNodeWorkload
from isvtest.workloads.slurm_sbatch import SlurmSbatchWorkload

__all__ = [
    "K8sGpuStressWorkload",
    "K8sNcclWorkload",
    "K8sNimHelmWorkload",
    "K8sNimInferenceWorkload",
    "SlurmGpuStressWorkload",
    "SlurmNcclMultiNodeWorkload",
    "SlurmSbatchWorkload",
]
