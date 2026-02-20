#!/usr/bin/env bash
# Teardown Kubernetes cluster - TEMPLATE (replace with your platform implementation)
#
# This script is called during the "teardown" phase. It must:
#   1. Check if teardown is enabled (TEARDOWN_ENABLED env var)
#   2. Destroy all cluster resources
#   3. Print a JSON object to stdout (all other output to stderr)
#
# Required JSON output (to stdout):
#   {
#     "success": true,
#     "platform": "kubernetes",
#     "message": "Cluster destroyed"
#   }
#
# When teardown is skipped (TEARDOWN_ENABLED != "true"):
#   {
#     "success": true,
#     "platform": "kubernetes",
#     "skipped": true,
#     "message": "Teardown skipped (set TEARDOWN_ENABLED=true to enable)"
#   }
#
# On failure, print JSON with "success": false and an "error" field.
#
# Environment Variables:
#   - TEARDOWN_ENABLED: Set to "true" to allow destruction (default: false)
#
# Reference implementation: ../../../stubs/aws/eks/teardown.sh

set -euo pipefail

# ─────────────────────────────────────────────────────────────────────
# Safety Check
# ─────────────────────────────────────────────────────────────────────

TEARDOWN_ENABLED="${TEARDOWN_ENABLED:-false}"

if [ "$TEARDOWN_ENABLED" != "true" ]; then
    echo ""                                            >&2
    echo "========================================="   >&2
    echo "  TEARDOWN SKIPPED - Resources Preserved"    >&2
    echo "========================================="   >&2
    echo ""                                            >&2
    echo "Cluster was NOT destroyed."                  >&2
    echo "To destroy, set TEARDOWN_ENABLED=true"       >&2
    echo ""                                            >&2

    cat << 'EOF'
{
  "success": true,
  "platform": "kubernetes",
  "skipped": true,
  "message": "Teardown skipped (set TEARDOWN_ENABLED=true to enable)"
}
EOF
    exit 0
fi

# ─────────────────────────────────────────────────────────────────────
# TODO: Replace this section with your cluster teardown logic
#
# This is where you destroy the cluster using your platform's tools.
# Common approaches:
#
#   - Terraform:
#       cd terraform/ && terraform destroy -auto-approve
#
#   - Platform CLI:
#       mycloud cluster delete --name "$CLUSTER_NAME" --force
#
#   - API calls:
#       curl -X DELETE https://api.mycloud.com/clusters/<id>
#
# WARNING: This permanently deletes all cluster resources!
#
# ─────────────────────────────────────────────────────────────────────

echo "=========================================" >&2
echo "  DESTROYING CLUSTER"                      >&2
echo "=========================================" >&2
echo ""                                          >&2

echo "ERROR: Not implemented - replace with your platform's cluster teardown" >&2

cat << 'EOF'
{
  "success": false,
  "platform": "kubernetes",
  "error": "Not implemented - replace with your platform's cluster teardown logic"
}
EOF

exit 1
