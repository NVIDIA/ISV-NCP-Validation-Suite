#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Set up a Kubernetes cluster with the provider's CSI drivers."""

import json
import os
import sys
from typing import Any

DEMO_MODE = os.environ.get("ISVCTL_DEMO_MODE") == "1"


def main() -> int:
    """Emit the provider-neutral cluster and StorageClass contract."""
    result: dict[str, Any] = {
        "success": False,
        "platform": "kubernetes",
        "kubeconfig_path": "",
        "csi": {
            "block_storage_class": "",
            "shared_fs_storage_class": "",
            "nfs_storage_class": "",
            "static_volume_handle": "",
            "static_driver_name": "",
            "static_volume_az": "",
        },
    }

    # TODO: Provision (or reuse) a cluster with your CSI drivers, then return
    # its kubeconfig and StorageClass names using this contract.
    if DEMO_MODE:
        result.update(
            {
                "success": True,
                "kubeconfig_path": "/tmp/isvctl-demo-kubeconfig",
                "csi": {
                    "block_storage_class": "demo-block",
                    "shared_fs_storage_class": "demo-shared",
                    "nfs_storage_class": "demo-nfs",
                    "static_volume_handle": "",
                    "static_driver_name": "",
                    "static_volume_az": "",
                },
            }
        )
    else:
        result["error"] = "Not implemented - set up a Kubernetes cluster with CSI installed"

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
