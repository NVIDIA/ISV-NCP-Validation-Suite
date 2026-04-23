#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

# Destroy the test node pool created by create_node_pool.sh.
#
# Runs `terraform destroy` on the isolated terraform-node-pool state. This
# runs before the cluster teardown so the node group's ENIs and instances
# are freed before the VPC comes down.
#
# Environment variables:
#   TF_AUTO_APPROVE   - "true" to skip confirmation (default: false)

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="${SCRIPT_DIR}/terraform-node-pool"

if ! command -v terraform &> /dev/null; then
    echo "Error: terraform not found" >&2
    exit 1
fi

# If the module was never applied (e.g. create step failed before
# `terraform apply`), there is no state to destroy. Report success so the
# overall teardown phase can proceed to the main cluster destroy.
if [ ! -f "${TF_DIR}/terraform.tfstate" ]; then
    echo "No node-pool state found at ${TF_DIR}/terraform.tfstate; nothing to destroy." >&2
    cat << 'EOF'
{
  "success": true,
  "platform": "kubernetes",
  "message": "Node pool state absent — nothing to destroy",
  "resources_deleted": []
}
EOF
    exit 0
fi

cd "${TF_DIR}"

echo "" >&2
echo "========================================" >&2
echo "  Destroying test node pool" >&2
echo "========================================" >&2

if [ ! -d ".terraform" ]; then
    terraform init >&2
fi

TF_AUTO_APPROVE="${TF_AUTO_APPROVE:-false}"
if [ "${TF_AUTO_APPROVE}" = "true" ]; then
    terraform destroy -auto-approve >&2
else
    terraform destroy >&2
fi

cat << 'EOF'
{
  "success": true,
  "platform": "kubernetes",
  "message": "Test node pool destroyed",
  "resources_deleted": ["aws_eks_node_group", "aws_iam_role"]
}
EOF
