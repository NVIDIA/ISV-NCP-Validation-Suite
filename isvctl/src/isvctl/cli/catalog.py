# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Catalog subcommand for isvctl.

Manage the test catalog: build, save, and upload to ISV Lab Service.
"""

import json
import logging
from pathlib import Path
from typing import Annotated

import typer
from isvtest.catalog import build_catalog, get_catalog_version

from isvctl.cli import setup_logging

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="catalog",
    help="Manage the test catalog for coverage tracking",
    no_args_is_help=True,
)


@app.command("push")
def push(
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable verbose logging"),
    ] = False,
    no_upload: Annotated[
        bool,
        typer.Option("--no-upload", help="Build and save locally without uploading"),
    ] = False,
) -> None:
    """Build the test catalog and upload it to ISV Lab Service.

    Discovers all validation tests, saves the catalog to
    _output/test_catalog.json, and uploads it to the backend.
    If the catalog for this version already exists, the upload
    is skipped.

    Examples:
        isvctl catalog push
        isvctl catalog push --no-upload
    """
    setup_logging(verbose)

    typer.echo("Building test catalog...")
    catalog_entries = build_catalog()
    catalog_version = get_catalog_version()
    typer.echo(f"  {len(catalog_entries)} tests (version: {catalog_version})")

    output_dir = Path("_output")
    output_dir.mkdir(parents=True, exist_ok=True)
    catalog_path = output_dir / "test_catalog.json"
    catalog_path.write_text(json.dumps({"isvTestVersion": catalog_version, "entries": catalog_entries}, indent=2))
    typer.echo(f"  Saved to: {catalog_path}")

    if no_upload:
        typer.echo("Skipping upload (--no-upload)")
        return

    from isvctl.reporting import check_upload_credentials, get_environment_config

    can_upload, client_id, client_secret = check_upload_credentials()
    if not can_upload or not client_id or not client_secret:
        typer.echo(
            typer.style("Error:", fg=typer.colors.RED) + " ISV_CLIENT_ID and/or ISV_CLIENT_SECRET not set",
            err=True,
        )
        raise typer.Exit(1)

    endpoint, ssa_issuer = get_environment_config()
    if not endpoint or not ssa_issuer:
        typer.echo(
            typer.style("Error:", fg=typer.colors.RED) + " ISV_SERVICE_ENDPOINT and/or ISV_SSA_ISSUER not set",
            err=True,
        )
        raise typer.Exit(1)

    from isvreporter.auth import get_jwt_token
    from isvreporter.client import upload_test_catalog

    jwt_token = get_jwt_token(ssa_issuer, client_id, client_secret)
    if upload_test_catalog(
        endpoint=endpoint,
        jwt_token=jwt_token,
        isv_test_version=catalog_version,
        entries=catalog_entries,
    ):
        typer.echo(typer.style("[OK]", fg=typer.colors.GREEN) + " Catalog push complete")
    else:
        typer.echo(typer.style("[FAIL]", fg=typer.colors.RED) + " Catalog upload failed")
        raise typer.Exit(1)
