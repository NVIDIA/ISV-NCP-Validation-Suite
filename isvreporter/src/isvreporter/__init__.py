# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""ISV Lab Test Results Reporter - report validation test results to ISV Lab Service."""

from isvreporter.config import get_endpoint, get_ssa_issuer
from isvreporter.version import get_version

__all__ = [
    "__version__",
    "get_endpoint",
    "get_ssa_issuer",
]

__version__ = get_version("isvreporter")
