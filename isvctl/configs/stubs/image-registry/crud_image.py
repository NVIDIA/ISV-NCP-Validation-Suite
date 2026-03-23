#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""CRUD custom OS images - TEMPLATE (replace with your platform implementation).

This script validates get, list, create, and delete operations on OS images.
Given an existing image_id (from the upload_image step), it should:

  1. GET    - Retrieve image details by ID
  2. LIST   - List images and verify the target appears
  3. CREATE - Create a new image (e.g., copy/clone the source)
  4. DELETE - Delete the created copy

Required JSON output:
{
    "success": true,
    "platform": "image_registry",
    "image_id": "<source-image-id>",
    "operations": {
        "get":    {"passed": true, "image_name": "...", "state": "available"},
        "list":   {"passed": true, "image_count": 2},
        "create": {"passed": true, "image_id": "<copy-image-id>"},
        "delete": {"passed": true}
    }
}

Usage:
    python crud_image.py --image-id <id> --region us-west-2

Reference implementation: ../aws/image-registry/crud_image.py
"""

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="CRUD custom OS images (template)")
    parser.add_argument("--image-id", required=True, help="Source image ID from upload_image step")
    parser.add_argument("--region", default="us-west-2", help="Cloud region")
    args = parser.parse_args()

    result: dict = {
        "success": False,
        "platform": "image_registry",
        "image_id": args.image_id,
        "operations": {
            "get": {"passed": False},
            "list": {"passed": False},
            "create": {"passed": False},
            "delete": {"passed": False},
        },
    }

    # TODO: Replace with your platform's image CRUD implementation
    result["error"] = "Not implemented - replace with your platform's image CRUD logic"
    print(json.dumps(result, indent=2))

    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
