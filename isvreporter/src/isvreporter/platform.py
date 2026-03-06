# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Platform constants and utilities for isvreporter.

Mirrors isvctl.config.platform for standalone isvreporter installations.
"""

from pathlib import Path

import yaml

# Valid platform types
KUBERNETES = "kubernetes"
SLURM = "slurm"
BARE_METAL = "bare_metal"

# Platform aliases (normalized to canonical names)
PLATFORM_ALIASES: dict[str, str] = {
    "k8s": KUBERNETES,
    "kubernetes": KUBERNETES,
    "slurm": SLURM,
    "bare_metal": BARE_METAL,
    "baremetal": BARE_METAL,
    "bare-metal": BARE_METAL,
}

DEFAULT_PLATFORM = KUBERNETES


def normalize_platform(platform: str | None) -> str:
    """Normalize a platform string to a canonical platform name.

    Args:
        platform: Platform string (e.g., 'k8s', 'kubernetes', 'baremetal')

    Returns:
        Normalized platform string ('kubernetes', 'slurm', or 'bare_metal')
    """
    if not platform:
        return DEFAULT_PLATFORM

    normalized = platform.lower().strip().replace("-", "_")
    return PLATFORM_ALIASES.get(normalized, DEFAULT_PLATFORM)


def get_platform_from_config(config_path: Path | str) -> str:
    """Extract and normalize platform from a config file.

    Args:
        config_path: Path to the YAML config file

    Returns:
        Normalized platform string ('kubernetes', 'slurm', or 'bare_metal')
    """
    try:
        with open(config_path) as f:
            config_data = yaml.safe_load(f)
        platform = config_data.get("tests", {}).get("platform", "")
        return normalize_platform(platform)
    except Exception:
        return DEFAULT_PLATFORM


def is_valid_platform(platform: str | None) -> bool:
    """Check if a platform string is valid (after normalization).

    Args:
        platform: Platform string to check

    Returns:
        True if the platform is valid, False otherwise
    """
    if not platform:
        return False
    normalized = platform.lower().strip().replace("-", "_")
    return normalized in PLATFORM_ALIASES
