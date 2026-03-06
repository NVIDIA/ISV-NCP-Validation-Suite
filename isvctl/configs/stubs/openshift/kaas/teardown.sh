#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

# OpenShift KaaS Teardown - Clean up test namespace
#
# Deletes the test namespace if it was created during validation.
# Does not deprovision the cluster itself.

set -eo pipefail

NAMESPACE="${K8S_NAMESPACE:-ncp-validation}"

echo "Cleaning up namespace ${NAMESPACE}..." >&2

kubectl delete namespace "${NAMESPACE}" --ignore-not-found 2>/dev/null || true

cat << EOF
{
  "success": true,
  "platform": "kubernetes",
  "resources_deleted": ["namespace/${NAMESPACE}"],
  "message": "Test namespace cleaned up"
}
EOF
