# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Dummy test to ensure pytest runs successfully."""

import isvtest.main


def test_dummy() -> None:
    """A simple dummy test that always passes."""
    assert True


def test_main_module_exists() -> None:
    """Test that the main module can be imported."""
    assert isvtest.main is not None
