# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Version resolution for all workspace packages.

The canonical version lives in each package's pyproject.toml. At runtime,
importlib.metadata reads it from installed package metadata (works in wheels,
editable installs, and airgapped environments after ``uv sync``).
"""

from importlib.metadata import PackageNotFoundError, version


def get_version(package_name: str) -> str:
    """Return the installed version of *package_name*, or ``"dev"`` if unavailable.

    Args:
        package_name: Distribution name (e.g. ``"isvreporter"``).

    Returns:
        Version string such as ``"1.2.3"`` or ``"dev"``.
    """
    try:
        return version(package_name)
    except PackageNotFoundError:
        return "dev"
