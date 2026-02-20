#!/bin/bash
# AWS EKS Teardown Stub - Destroys AWS infrastructure using Terraform
#
# Environment Variables:
#   - AWS_TEARDOWN_ENABLED: Set to "true" to enable teardown (default: false)
#   - TF_AUTO_APPROVE: Set to "true" to skip confirmation (default: false)
#
# Warning: This will permanently delete all AWS resources!

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="${SCRIPT_DIR}/terraform"

# Safety check
AWS_TEARDOWN_ENABLED="${AWS_TEARDOWN_ENABLED:-false}"
AWS_REGION="${AWS_REGION:-us-west-2}"
if [ "$AWS_TEARDOWN_ENABLED" != "true" ]; then
    echo "" >&2
    echo "========================================" >&2
    echo "  TEARDOWN SKIPPED - Resources Preserved" >&2
    echo "========================================" >&2
    echo "" >&2
    echo "AWS infrastructure was NOT destroyed." >&2
    echo "Your EKS cluster and resources are still running." >&2
    echo "" >&2
    echo "To destroy resources, run with:" >&2
    echo "  AWS_TEARDOWN_ENABLED=true TF_AUTO_APPROVE=true \\" >&2
    echo "    uv run isvctl test run -f isvctl/configs/aws/eks.yaml --phase teardown" >&2
    echo "" >&2
    echo "Or manually:" >&2
    echo "  cd isvctl/configs/stubs/aws/eks/terraform" >&2
    echo "  terraform destroy" >&2
    echo "" >&2
    # Output JSON for orchestration framework
    cat << EOF
{
  "success": true,
  "platform": "kubernetes",
  "skipped": true,
  "message": "Teardown skipped (set AWS_TEARDOWN_ENABLED=true to enable)",
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
