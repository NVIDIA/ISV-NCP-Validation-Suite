# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Common utility functions for validation checks."""

import shutil
from pathlib import Path


def stub_exists(stub_path: str) -> bool:
    """Check if a stub script exists and is a file.

    Args:
        stub_path: Path to the stub script (relative or absolute).

    Returns:
        True if the stub exists and is a file, False otherwise.
    """
    path = Path(stub_path)
    return path.exists() and path.is_file()


def command_exists(command: str) -> bool:
    """Check if a command is available in PATH.

    Args:
        command: Name of the command to check (e.g., 'kubectl', 'sinfo').

    Returns:
        True if the command is available, False otherwise.
    """
    return shutil.which(command) is not None


def truncate(text: str, *, limit: int = 80) -> str:
    """Return ``text`` shortened to at most ``limit`` characters with an ellipsis marker."""
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."
