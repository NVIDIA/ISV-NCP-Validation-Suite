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
