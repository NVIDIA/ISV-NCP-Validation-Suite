# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for version module."""

import subprocess
from collections.abc import Iterator
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from unittest.mock import patch

import pytest

from isvreporter.version import (
    _repository_root,
    describe_checkout,
    get_version,
    is_released_version,
)


@pytest.fixture(autouse=True)
def _uncached_describe() -> Iterator[None]:
    """Drop the describe cache so each test starts from a cold lookup.

    The result is cached for the life of the process, and these tests run
    inside a checkout that would otherwise answer every one of them.
    """
    describe_checkout.cache_clear()
    yield
    describe_checkout.cache_clear()


def _describe(output: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=f"{output}\n", stderr="")


class TestGetVersion:
    """Tests for get_version function."""

    def test_returns_metadata_version_when_not_in_a_checkout(self) -> None:
        """Installed from a wheel, the metadata version is all there is."""
        with patch("isvreporter.version._repository_root", return_value=None):
            with patch("isvreporter.version.version", return_value="1.2.3") as mock:
                assert get_version("isvreporter") == "1.2.3"
                mock.assert_called_once_with("isvreporter")

    def test_returns_dev_when_package_not_found(self) -> None:
        """When metadata lookup fails and there is no checkout, return 'dev'."""
        with patch("isvreporter.version._repository_root", return_value=None):
            with patch("isvreporter.version.version", side_effect=PackageNotFoundError("nope")):
                assert get_version("nonexistent") == "dev"

    def test_a_clean_release_tag_reports_the_bare_version(self) -> None:
        """On the tag itself there is no provenance to add."""
        with patch("isvreporter.version._repository_root", return_value=Path("/repo")):
            with patch("subprocess.run", return_value=_describe("v0.10.0-0-g6634373")):
                assert get_version("isvtest") == "0.10.0"

    def test_commits_past_a_tag_carry_the_distance_and_commit(self) -> None:
        """The lab-42 case: 0.9.0 plus three commits is not 0.9.0."""
        with patch("isvreporter.version._repository_root", return_value=Path("/repo")):
            with patch("subprocess.run", return_value=_describe("v0.9.0-3-g08339c7")):
                assert get_version("isvtest") == "0.9.0.post3+g08339c7"

    def test_uncommitted_changes_are_marked_dirty(self) -> None:
        """A dirty tree is not the tag even at distance zero."""
        with patch("isvreporter.version._repository_root", return_value=Path("/repo")):
            with patch("subprocess.run", return_value=_describe("v0.9.0-0-g6634373-dirty")):
                assert get_version("isvtest") == "0.9.0.post0+g6634373.dirty"

    def test_the_tag_beats_stale_installed_metadata(self) -> None:
        """Metadata is written at install time and goes stale when the tree moves."""
        with patch("isvreporter.version._repository_root", return_value=Path("/repo")):
            with patch("subprocess.run", return_value=_describe("v0.10.0-0-g6634373")):
                with patch("isvreporter.version.version", return_value="0.9.0"):
                    assert get_version("isvtest") == "0.10.0"

    @pytest.mark.parametrize(
        "failure",
        [
            OSError("git not installed"),
            subprocess.CalledProcessError(128, "git"),
            subprocess.TimeoutExpired("git", 5),
        ],
    )
    def test_a_failed_lookup_falls_back_rather_than_breaking_the_run(self, failure: Exception) -> None:
        """No git, no tags, or a hung call must never fail a reporting call."""
        with patch("isvreporter.version._repository_root", return_value=Path("/repo")):
            with patch("subprocess.run", side_effect=failure):
                with patch("isvreporter.version.version", return_value="0.9.0"):
                    assert get_version("isvtest") == "0.9.0"

    def test_unparseable_describe_output_falls_back(self) -> None:
        """A tag scheme this workspace does not use must not become the version."""
        with patch("isvreporter.version._repository_root", return_value=Path("/repo")):
            with patch("subprocess.run", return_value=_describe("some-other-scheme")):
                with patch("isvreporter.version.version", return_value="0.9.0"):
                    assert get_version("isvtest") == "0.9.0"

    def test_the_checkout_is_described_once_per_process(self) -> None:
        """Every package's lookup would otherwise spawn its own git."""
        with patch("isvreporter.version._repository_root", return_value=Path("/repo")):
            with patch("subprocess.run", return_value=_describe("v0.9.0-3-g08339c7")) as mock:
                get_version("isvtest")
                get_version("isvctl")
                get_version("isvreporter")
                assert mock.call_count == 1


class TestRepositoryRoot:
    """Which trees count as this workspace's own checkout."""

    @pytest.mark.parametrize(
        "install_path",
        [
            # A wheel in a virtualenv created inside the other repository.
            ".venv/lib/python3.12/site-packages/isvreporter/version.py",
            # `--target`, which lands anywhere and carries no segment to recognise.
            "libs/isvreporter/version.py",
        ],
    )
    def test_an_installed_copy_claims_no_checkout(self, tmp_path: Path, install_path: str) -> None:
        """A partner's tags must not be reported as ours.

        Installing into an environment under another repository is ordinary, and
        that repository's `v*` tag would describe just as cleanly as ours. The
        foreign repository is built for real, so the walk has something to find
        and the test fails if the module stops checking what it found.
        """
        foreign = tmp_path / "their-repo"
        (foreign / ".git").mkdir(parents=True)
        module = foreign / install_path
        module.parent.mkdir(parents=True)
        module.write_text("")

        with patch("isvreporter.version.__file__", str(module)):
            assert _repository_root() is None

    def test_a_source_tree_is_the_checkout(self, tmp_path: Path) -> None:
        """Including an editable install, whose files stay in the tree."""
        root = tmp_path / "client"
        package = root / "isvreporter" / "src" / "isvreporter"
        package.mkdir(parents=True)
        # The worktree spelling: .git as a file rather than a directory.
        (root / ".git").write_text("gitdir: /elsewhere\n")
        module = package / "version.py"
        module.write_text("")

        with patch("isvreporter.version.__file__", str(module)):
            assert _repository_root() == root.resolve()


class TestIsReleasedVersion:
    """Tests for the rule the service applies to the reported version."""

    @pytest.mark.parametrize("candidate", ["0.9.0", "1.0", "0.10.0", "2", "1.0rc1"])
    def test_release_numbers_are_released(self, candidate: str) -> None:
        assert is_released_version(candidate)

    @pytest.mark.parametrize(
        "candidate",
        ["0.9.0.post3+g08339c7", "0.9.0.post0+g6634373.dirty", "dev", "0.9.0.dev1"],
    )
    def test_builds_between_releases_are_not(self, candidate: str) -> None:
        assert not is_released_version(candidate)
