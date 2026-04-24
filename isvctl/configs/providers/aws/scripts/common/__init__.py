# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Shared Python utilities for AWS stub scripts.

Every AWS script reaches this package via a single ``sys.path`` entry -
``providers/aws/scripts/`` - so ``from common.X import Y`` resolves
without any namespace-package juggling. Modules:

- ``ec2``: key pair / security group / public IP helpers
- ``errors``: AWS error classification, ``delete_with_retry``, and the
  ``handle_aws_errors`` decorator used by every script's ``main()``
- ``ssh_utils``: ``wait_for_ssh`` reachability probe (shared with no
  other provider today; moved here from ``providers/shared/`` so all
  AWS imports live under a single ``common`` package)
- ``serial_console``: boto3 serial-console connectivity helper
- ``vpc``: VPC / subnet / SG creation + retry-backed teardown helpers
"""
