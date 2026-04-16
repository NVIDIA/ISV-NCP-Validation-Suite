# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

import json
import shlex
from collections.abc import Iterable
from typing import ClassVar
from urllib.parse import urlsplit

from isvtest.core.k8s import get_kubectl_command
from isvtest.core.validation import BaseValidation

DEFAULT_REQUIRED_FIELDS = [
    "issuer",
    "jwks_uri",
    "response_types_supported",
    "subject_types_supported",
    "id_token_signing_alg_values_supported",
]


class K8sOidcIssuerCheck(BaseValidation):
    """Validate the cluster's OIDC discovery endpoint for workload identity federation."""

    description: ClassVar[str] = (
        "Verify the cluster exposes a valid OIDC Issuer endpoint for workload identity federation."
    )
    markers: ClassVar[list[str]] = ["kubernetes"]

    def run(self) -> None:
        """Fetch the OIDC discovery document and validate its shape and issuer URL."""
        required_fields_config = self.config.get("required_fields", DEFAULT_REQUIRED_FIELDS)
        if isinstance(required_fields_config, str):
            required_fields = [required_fields_config]
        elif isinstance(required_fields_config, Iterable):
            required_fields = list(required_fields_config)
            if any(not isinstance(field, str) or not field for field in required_fields):
                self.set_failed("Invalid 'required_fields' config: expected a string or iterable of non-empty strings.")
                return
        else:
            self.set_failed("Invalid 'required_fields' config: expected a string or iterable of non-empty strings.")
            return

        kubectl_parts = get_kubectl_command()
        kubectl_base = " ".join(shlex.quote(part) for part in kubectl_parts)

        cmd = f"{kubectl_base} get --raw /.well-known/openid-configuration"
        result = self.run_command(cmd)

        if result.exit_code != 0:
            self.set_failed(f"Failed to query OIDC discovery endpoint: {result.stderr}")
            return

        try:
            oidc_config = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            self.set_failed(f"Failed to parse OIDC discovery response as JSON: {e}")
            return

        if not isinstance(oidc_config, dict):
            self.set_failed("OIDC discovery response must be a JSON object.")
            return

        missing_fields = [f for f in required_fields if f not in oidc_config]
        if missing_fields:
            self.set_failed(f"OIDC discovery response missing required fields: {', '.join(missing_fields)}")
            return

        issuer = oidc_config.get("issuer")
        if not isinstance(issuer, str):
            self.set_failed(f"OIDC issuer is not a valid HTTPS URL: {issuer}")
            return

        parsed = urlsplit(issuer)
        if parsed.scheme != "https" or not parsed.netloc:
            self.set_failed(f"OIDC issuer is not a valid HTTPS URL: {issuer}")
            return

        self.log.info(f"OIDC issuer: {issuer}")
        self.set_passed(f"OIDC discovery endpoint is valid with issuer: {issuer}")
