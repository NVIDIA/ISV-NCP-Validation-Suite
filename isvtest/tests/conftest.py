# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Auto-apply unit marker to all tests in tests/ directory."""

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register the unit marker to avoid warnings."""
    config.addinivalue_line("markers", "unit: Unit tests for library code")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Automatically add 'unit' marker to all tests in tests/ directory.

    Only matches isvtest/tests/, not isvtest/src/isvtest/tests/
    """
    for item in items:
        path_str = str(item.fspath)
        # Only mark tests that are in isvtest/tests/ (not in src/isvtest/tests/)
        if "/tests/" in path_str and "/src/isvtest/tests/" not in path_str:
            item.add_marker(pytest.mark.unit)
