#!/usr/bin/env python3
"""Install an OS install configuration on a bare-metal system.

Provider-agnostic template — replace the TODO section with your platform's
bare-metal provisioning API calls to install an OS using a config profile
(e.g., iPXE config, Carbide profile).

Required JSON output:
{
    "success":        bool — true if BM instance provisioned and running,
    "platform":       str  — "image_registry",
    "instance_id":    str  — bare-metal instance identifier,
    "config_id":      str  — install config used for provisioning,
    "instance_state": str  — "running",
    "error":          str  — (optional) error message, present when success is false
}

Usage:
    python install_config_bm.py --config-id cfg-xxx --region us-west-2

AWS reference implementation:
    ../../../stubs/aws/image-registry/install_config_bm.py
"""

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Install OS config on bare-metal")
    parser.add_argument("--config-id", required=True, help="Install config ID from the registry")
    parser.add_argument("--region", required=True, help="Cloud region / availability zone")
    args = parser.parse_args()

    result: dict = {
        "success": False,
        "platform": "image_registry",
        "instance_id": "",
        "config_id": args.config_id,
        "instance_state": "",
    }

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  TODO: Replace this block with your platform's implementation    ║
    # ║                                                                  ║
    # ║  1. Provision a bare-metal node using the install config         ║
    # ║     instance = provision_bm_from_config(                         ║
    # ║         config_id=args.config_id, region=args.region,            ║
    # ║     )                                                            ║
    # ║     result["instance_id"] = instance.id                          ║
    # ║                                                                  ║
    # ║  2. Wait for the node to reach "running" state                   ║
    # ║     wait_for_running(instance.id)                                ║
    # ║     result["instance_state"] = "running"                         ║
    # ║                                                                  ║
    # ║  3. Set result["success"] = True                                 ║
    # ╚══════════════════════════════════════════════════════════════════╝

    result["error"] = "Not implemented - replace with your platform's BM config install logic"

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
