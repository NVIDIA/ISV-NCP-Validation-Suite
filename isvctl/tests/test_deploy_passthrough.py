# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for forwarding a deploy's pytest args to the remote test run."""

from isvctl.cli.deploy import _pytest_passthrough


def test_passthrough_carries_the_separator() -> None:
    """Without `--`, `test run` reads a bare pytest flag as an unknown isvctl option."""
    assert _pytest_passthrough(["-v", "-s", "-k", "K8sNodeReadyCheck"]) == "-- -v -s -k K8sNodeReadyCheck"


def test_passthrough_is_empty_without_args() -> None:
    """A deploy with no pytest args leaves no dangling separator on the command line."""
    assert _pytest_passthrough([]) == ""


def test_passthrough_quotes_a_multi_word_expression() -> None:
    """The remote shell must receive one -k argument, not three words."""
    assert _pytest_passthrough(["-k", "A or B"]) == "-- -k 'A or B'"
