#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

# AWS EKS Teardown Stub - Destroys AWS infrastructure using Terraform
#
# Environment Variables:
#   - AWS_SKIP_TEARDOWN: Set to "true" to skip teardown and preserve resources (default: false)
#   - TF_AUTO_APPROVE: Set to "true" to skip confirmation (default: false)
#
# Warning: This will permanently delete all AWS resources!

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="${SCRIPT_DIR}/terraform"

AWS_SKIP_TEARDOWN="${AWS_SKIP_TEARDOWN:-false}"
AWS_REGION="${AWS_REGION:-us-west-2}"
if [ "$AWS_SKIP_TEARDOWN" = "true" ]; then
    echo "" >&2
    echo "========================================" >&2
    echo "  TEARDOWN SKIPPED - Resources Preserved" >&2
    echo "========================================" >&2
    echo "" >&2
    echo "AWS infrastructure was NOT destroyed." >&2
    echo "Your EKS cluster and resources are still running." >&2
    echo "" >&2
    echo "To destroy resources, run without AWS_SKIP_TEARDOWN:" >&2
    echo "  uv run isvctl test run -f isvctl/configs/providers/aws/config/eks.yaml --phase teardown" >&2
    echo "" >&2
    echo "Or manually:" >&2
    echo "  cd isvctl/configs/providers/aws/scripts/eks/terraform" >&2
    echo "  terraform destroy" >&2
    echo "" >&2
    cat << EOF
{
  "success": true,
  "platform": "kubernetes",
  "skipped": true,
  "message": "Teardown skipped (AWS_SKIP_TEARDOWN=true)",
  "aws": {
    "region": "${AWS_REGION}"
  }
}
EOF
    exit 0
fi

# Check terraform
if ! command -v terraform &> /dev/null; then
    echo "Error: terraform not found" >&2
    exit 1
fi

cd "$TERRAFORM_DIR"

echo "" >&2
echo "========================================" >&2
echo "  DESTROYING AWS INFRASTRUCTURE" >&2
echo "========================================" >&2
echo "" >&2

# Initialize if needed
if [ ! -d ".terraform" ]; then
    echo "Initializing Terraform..." >&2
    terraform init >&2
fi

# Destroy
TF_AUTO_APPROVE="${TF_AUTO_APPROVE:-false}"
if [ "$TF_AUTO_APPROVE" = "true" ]; then
    echo "Running terraform destroy (auto-approved)..." >&2
    terraform destroy -auto-approve >&2
else
    echo "Running terraform destroy..." >&2
    terraform destroy >&2
fi

echo "" >&2
echo "========================================" >&2
echo "  TEARDOWN COMPLETE" >&2
echo "========================================" >&2
echo "All AWS resources have been destroyed." >&2

# Output JSON result
AWS_REGION="${AWS_REGION:-us-west-2}"
cat << EOF
{
  "success": true,
  "platform": "kubernetes",
  "message": "EKS cluster and AWS resources destroyed",
  "resources_deleted": ["eks_cluster", "node_groups", "vpc_resources"],
  "aws": {
    "region": "${AWS_REGION}"
  }
}
EOF
