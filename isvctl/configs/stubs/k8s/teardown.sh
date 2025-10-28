#!/bin/bash
# K8s Teardown Stub - No-op for existing clusters
# For managed clusters, this could call cloud provider APIs to destroy the cluster
set -eo pipefail

echo "Teardown: No action taken (existing cluster)" >&2
