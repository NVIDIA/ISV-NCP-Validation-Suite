"""Platform constants and utilities for isvreporter.

Mirrors isvctl.config.platform for standalone isvreporter installations.
"""

from pathlib import Path

import yaml

# Canonical platform types (uppercase, matching backend enums)
KUBERNETES = "KUBERNETES"
SLURM = "SLURM"
BARE_METAL = "BARE_METAL"
CONTROL_PLANE = "CONTROL_PLANE"
IAM = "IAM"
NETWORK = "NETWORK"
VM = "VM"
IMAGE_REGISTRY = "IMAGE_REGISTRY"

ALL_PLATFORMS = {
    KUBERNETES,
    SLURM,
    BARE_METAL,
    CONTROL_PLANE,
    IAM,
    NETWORK,
    VM,
    IMAGE_REGISTRY,
}

# Platform aliases (normalized to canonical uppercase names)
PLATFORM_ALIASES: dict[str, str] = {
    "k8s": KUBERNETES,
    "kubernetes": KUBERNETES,
    "slurm": SLURM,
    "bare_metal": BARE_METAL,
    "bm": BARE_METAL,
    "control_plane": CONTROL_PLANE,
    "iam": IAM,
    "network": NETWORK,
    "vm": VM,
    "image_registry": IMAGE_REGISTRY,
}

DEFAULT_PLATFORM = KUBERNETES


def normalize_platform(platform: str | None) -> str:
    """Normalize a platform string to a canonical uppercase name.

    Args:
        platform: Platform string (e.g., 'k8s', 'kubernetes', 'KUBERNETES',
            'iam', 'control_plane')

    Returns:
        Canonical uppercase platform string (e.g., 'KUBERNETES', 'IAM')
    """
    if not platform:
        return DEFAULT_PLATFORM

    cleaned = platform.strip()

    if cleaned.upper() in ALL_PLATFORMS:
        return cleaned.upper()

    normalized = cleaned.lower().replace("-", "_")
    return PLATFORM_ALIASES.get(normalized, DEFAULT_PLATFORM)


def get_platform_from_config(config_path: Path | str) -> str:
    """Extract and normalize platform from a config file.

    Args:
        config_path: Path to the YAML config file

    Returns:
        Canonical uppercase platform string
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
    cleaned = platform.strip()
    if cleaned.upper() in ALL_PLATFORMS:
        return True
    normalized = cleaned.lower().replace("-", "_")
    return normalized in PLATFORM_ALIASES
