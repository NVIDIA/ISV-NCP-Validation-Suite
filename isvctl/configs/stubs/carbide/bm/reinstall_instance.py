#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Reinstall OS on a Carbide bare-metal instance (not supported).

Carbide does not currently support in-place OS reinstall. This stub
outputs a success result with a skip note so the template validation
passes gracefully.

Usage:
    python reinstall_instance.py

Output JSON:
{
    "success": true,
    "platform": "bm",
    "skipped": true,
    "message": "Reinstall not supported by Carbide"
}
"""

import argparse
import json
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Reinstall Carbide BM instance (not supported)")
    parser.add_argument("--region", default=os.environ.get("CARBIDE_REGION", ""))
    parser.parse_args()

    result = {
        "success": True,
        "platform": "bm",
        "skipped": True,
        "message": "Reinstall not supported by Carbide",
    }

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
