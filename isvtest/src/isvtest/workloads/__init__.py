"""ISV workload validations.

This module contains longer-running workload tests that deploy real workloads
to validate GPU functionality and performance.
"""

from isvtest.workloads.k8s_nccl import K8sNcclWorkload
from isvtest.workloads.k8s_nim import K8sNimInferenceWorkload
from isvtest.workloads.k8s_nim_helm import K8sNimHelmWorkload
from isvtest.workloads.k8s_platform_validator import (
    K8sPlatformValidatorBase,
    K8sPlatformValidatorFunctional,
    K8sPlatformValidatorPerformance,
)
from isvtest.workloads.k8s_stress import K8sGpuStressWorkload
from isvtest.workloads.slurm_gpu_stress import SlurmGpuStressWorkload
from isvtest.workloads.slurm_nccl_multinode import SlurmNcclMultiNodeWorkload
from isvtest.workloads.slurm_sbatch import SlurmSbatchWorkload

__all__ = [
    "K8sGpuStressWorkload",
    "K8sNcclWorkload",
    "K8sNimHelmWorkload",
    "K8sNimInferenceWorkload",
    "K8sPlatformValidatorBase",
    "K8sPlatformValidatorFunctional",
    "K8sPlatformValidatorPerformance",
    "SlurmGpuStressWorkload",
    "SlurmNcclMultiNodeWorkload",
    "SlurmSbatchWorkload",
]
