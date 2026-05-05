# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Unit tests for the catalog CLI subcommand."""

import json
from unittest.mock import patch

from typer.testing import CliRunner

from isvctl.cli.catalog import app

runner = CliRunner()

_FAKE_ENTRIES = [
    {
        "name": "AlphaCheck",
        "description": "Alpha description",
        "markers": ["kubernetes"],
        "module": "isvtest.validations.alpha",
        "platforms": ["KUBERNETES"],
    },
    {
        "name": "BetaCheck",
        "description": "",
        "markers": [],
        "module": "isvtest.validations.beta",
        "platforms": [],
    },
]


def test_catalog_help() -> None:
    """Top-level catalog help mentions the new list command."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "list" in result.output


def test_catalog_list_table() -> None:
    """`catalog list` renders a table containing the discovered tests."""
    with (
        patch("isvctl.cli.catalog.build_catalog", return_value=_FAKE_ENTRIES),
        patch("isvctl.cli.catalog.get_catalog_version", return_value="1.2.3"),
    ):
        result = runner.invoke(app, ["list"])

    assert result.exit_code == 0, result.output
    assert "AlphaCheck" in result.output
    assert "BetaCheck" in result.output
    assert "1.2.3" in result.output


def test_catalog_list_json() -> None:
    """`catalog list --json` emits parseable JSON matching the saved artifact shape."""
    with (
        patch("isvctl.cli.catalog.build_catalog", return_value=_FAKE_ENTRIES),
        patch("isvctl.cli.catalog.get_catalog_version", return_value="1.2.3"),
    ):
        result = runner.invoke(app, ["list", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["isvTestVersion"] == "1.2.3"
    assert payload["entries"] == _FAKE_ENTRIES


def test_catalog_list_unreleased_json() -> None:
    """`catalog list --unreleased` emits only entries missing from the release manifest."""
    with (
        patch("isvctl.cli.catalog.build_catalog", return_value=_FAKE_ENTRIES) as build_catalog,
        patch("isvctl.cli.catalog.load_released_tests", return_value={"AlphaCheck"}),
        patch("isvctl.cli.catalog.get_catalog_version", return_value="1.2.3"),
    ):
        result = runner.invoke(app, ["list", "--unreleased", "--json"])

    assert result.exit_code == 0, result.output
    build_catalog.assert_called_once_with(released_only=False)
    payload = json.loads(result.output)
    assert payload["entries"] == [_FAKE_ENTRIES[1]]
