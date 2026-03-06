# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Configuration for ISV Lab Service."""

import os


def get_endpoint() -> str:
    """Get ISV Lab Service endpoint from environment.

    Returns:
        The endpoint URL from ISV_SERVICE_ENDPOINT env var, or empty string if not set.
    """
    return os.environ.get("ISV_SERVICE_ENDPOINT", "")


def get_ssa_issuer() -> str:
    """Get SSA issuer URL from environment.

    Returns:
        The SSA issuer URL from ISV_SSA_ISSUER env var, or empty string if not set.
    """
    return os.environ.get("ISV_SSA_ISSUER", "")
