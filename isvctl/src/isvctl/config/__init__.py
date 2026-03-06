# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Configuration management for isvctl."""

from isvctl.config.merger import merge_yaml_files
from isvctl.config.output_schemas import (
    get_schema,
    get_schema_for_step,
    list_schemas,
    list_step_mappings,
    register_schema,
    register_step_mapping,
    validate_output,
)
from isvctl.config.schema import (
    CommandConfig,
    CommandOutput,
    KubernetesOutput,
    LabConfig,
    PlatformCommands,
    RunConfig,
    SlurmOutput,
    StepConfig,
    ValidationConfig,
)

__all__ = [
    "CommandConfig",
    "CommandOutput",
    "KubernetesOutput",
    "LabConfig",
    "PlatformCommands",
    "RunConfig",
    "SlurmOutput",
    "StepConfig",
    "ValidationConfig",
    "get_schema",
    "get_schema_for_step",
    "list_schemas",
    "list_step_mappings",
    "merge_yaml_files",
    "register_schema",
    "register_step_mapping",
    "validate_output",
]
