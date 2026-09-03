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

"""Tests for the catalog module."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from isvtest.catalog import (
    CATALOG_SCHEMA_VERSION,
    _assert_disjoint_vocabulary,
    build_capability_vocabulary,
    build_catalog,
    build_suite_vocabulary,
    catalog_digest,
    catalog_document,
    get_catalog_version,
)
from isvtest.core.validation import BaseValidation


class ExplicitLabelCatalogCheck(BaseValidation):
    """Catalog fixture whose labels are supplied by the YAML wiring scan."""

    description = "Explicit labels"

    def run(self) -> None:
        """Mark the validation passed."""
        self.set_passed()


class TestCatalogDocument:
    """Tests for capability vocabulary and the versioned catalog envelope."""

    def test_derives_capabilities_from_platform_suites(self) -> None:
        """Only real platform suite keys are declarable capabilities."""
        assert build_capability_vocabulary() == ["bare_metal", "kubernetes", "slurm", "vm"]

    def test_derives_suite_vocabulary_from_plain_suites(self) -> None:
        """Plain suite YAML files are listed separately from platform suites."""
        suites = build_suite_vocabulary()
        assert "iam" in suites
        assert "storage" in suites
        assert "kubernetes" not in suites
        assert "vm" not in suites

    def test_catalog_document_wraps_entries_with_metadata(self) -> None:
        """The envelope carries schema version, package version, and axis lists."""
        entries = [{"name": "X", "labels": ["iam"]}]
        doc = catalog_document(entries, "1.2.3")
        assert doc["schemaVersion"] == CATALOG_SCHEMA_VERSION
        assert doc["isvTestVersion"] == "1.2.3"
        assert doc["entries"] == entries
        assert doc["capabilities"] == build_capability_vocabulary()
        assert doc["suites"] == build_suite_vocabulary()
        # The axis is named `capabilities`; the former `platforms` spelling is gone.
        assert "platforms" not in doc
        # The label universe is intentionally not summarized at the top level.
        assert "labels" not in doc

    def test_disjoint_vocabulary_accepts_distinct_namespaces(self) -> None:
        """Plain suite names that are not capability words pass the guard."""
        _assert_disjoint_vocabulary(["vm", "kubernetes"], ["storage", "iam", "network"])

    def test_disjoint_vocabulary_rejects_suite_named_after_capability(self) -> None:
        """A plain suite named after any declarable capability is a namespace collision."""
        with pytest.raises(ValueError, match="kubernetes"):
            _assert_disjoint_vocabulary(["vm", "kubernetes"], ["storage", "kubernetes"])

    def test_disjoint_vocabulary_rejects_undeclared_capability_word(self) -> None:
        """Collision is checked against the full reserved set, not just declared platforms."""
        with pytest.raises(ValueError, match="slurm"):
            _assert_disjoint_vocabulary(["vm"], ["slurm"])


class TestBuildCatalog:
    """Tests for build_catalog function."""

    def test_entries_have_suite_contract(self) -> None:
        """Catalog rows expose suite placement and requirement metadata."""
        catalog = build_catalog(released_only=False)
        names = [entry["name"] for entry in catalog]
        assert catalog
        assert len(names) == len(set(names))
        for entry in catalog:
            assert set(entry) == {
                "name",
                "description",
                "labels",
                "test_ids",
                "source",
                "suite",
                "capability",
                "requires",
            }
            assert isinstance(entry["source"], str)
            assert isinstance(entry["requires"], list)
            if entry["capability"]:
                assert entry["requires"] == []

    def test_extract_checks_supports_direct_dict_category_form(self, tmp_path) -> None:
        """Direct dict category wiring is included in catalog config scans."""
        from isvtest.catalog import _extract_checks_from_config

        config = tmp_path / "direct-dict.yaml"
        config.write_text(
            """\
tests:
  validations:
    direct:
      DirectCheck:
        labels: ["network"]
      EmptyParamsCheck: {}
""",
            encoding="utf-8",
        )

        assert _extract_checks_from_config(config) == ["DirectCheck", "EmptyParamsCheck"]

    def test_extract_check_test_ids_excludes_na_and_blanks(self, tmp_path) -> None:
        """Wiring test_ids are extracted per check, with "N/A"/empty dropped."""
        from isvtest.catalog import _extract_check_test_ids_from_config

        config = tmp_path / "test-ids.yaml"
        config.write_text(
            """\
tests:
  validations:
    sample:
      checks:
        MappedCheck:
          test_id: "SEC07-01"
        GapCheck:
          test_id: "N/A"
        BlankCheck:
          test_id: ""
        NoIdCheck: {}
""",
            encoding="utf-8",
        )

        assert _extract_check_test_ids_from_config(config) == {"MappedCheck": {"SEC07-01"}}

    def test_entries_expose_wired_test_ids(self) -> None:
        """Catalog entries carry the plan ids declared on their wiring."""
        catalog = build_catalog(released_only=False)
        by_name = {e["name"]: e for e in catalog}

        # Every entry has a list-of-strings test_ids and never the "N/A" sentinel.
        for entry in catalog:
            assert isinstance(entry["test_ids"], list)
            assert all(isinstance(tid, str) for tid in entry["test_ids"])
            assert "N/A" not in entry["test_ids"]

        # Single mappings retain their requirement and suite placement.
        assert by_name["MfaEnforcedCheck"]["test_ids"] == ["SEC07-01"]
        assert by_name["MfaEnforcedCheck"]["suite"] == "security"
        assert by_name["MfaEnforcedCheck"]["requires"] == []

    def test_released_only_filters_catalog(self) -> None:
        """Default catalog generation excludes tests not in the release manifest."""
        with patch("isvtest.catalog.load_released_test_filter", return_value={"MfaEnforcedCheck"}):
            catalog = build_catalog()

        assert catalog
        assert all(entry["name"].startswith("MfaEnforcedCheck") for entry in catalog)

    def test_unreleased_env_includes_full_catalog(self) -> None:
        """When the release filter is disabled, default catalog generation includes all tests.

        Composites are the unreleased entries in practice: they are added to the
        release manifest by a release commit, not by the PR that wires them.
        """
        with patch("isvtest.catalog.load_released_test_filter", return_value=None):
            catalog = build_catalog()

        names = {e["name"] for e in catalog}
        assert "MfaEnforcedCheck" in names
        assert "VolumeDeletedCheck" in names

    def test_labels_are_lists_of_strings(self) -> None:
        """Test that labels are lists of strings."""
        catalog = build_catalog()
        for entry in catalog:
            for label in entry["labels"]:
                assert isinstance(label, str)

    def test_catalog_emits_explicit_labels(self) -> None:
        """Per-wiring YAML labels are surfaced as catalog tag metadata."""
        with (
            patch("isvtest.catalog.discover_all_tests", return_value=[ExplicitLabelCatalogCheck]),
            patch(
                "isvtest.catalog._build_suite_map",
                return_value={
                    "ExplicitLabelCatalogCheck": {
                        "suite": "demo",
                        "capability": None,
                        "requires": ["vm", "bare_metal"],
                        "composite": False,
                        "description": "",
                    }
                },
            ),
            patch(
                "isvtest.catalog.build_label_map",
                return_value={"ExplicitLabelCatalogCheck": {"accelerator", "long_running"}},
            ),
            patch("isvtest.catalog.build_test_id_map", return_value={}),
            patch("isvtest.catalog.load_released_test_filter", return_value=None),
        ):
            catalog = build_catalog()

        assert catalog == [
            {
                "name": "ExplicitLabelCatalogCheck",
                "description": "Explicit labels",
                "labels": ["accelerator", "long_running"],
                "test_ids": [],
                "source": __name__,
                "suite": "demo",
                "capability": None,
                "requires": ["vm", "bare_metal"],
            }
        ]

    def test_composite_entry_describes_itself(self) -> None:
        """A composite has no class, so its description comes from the wiring."""
        with (
            patch("isvtest.catalog.discover_all_tests", return_value=[ExplicitLabelCatalogCheck]),
            patch(
                "isvtest.catalog._build_suite_map",
                return_value={
                    "DemoComposedCheck": {
                        "suite": "demo",
                        "capability": None,
                        "requires": [],
                        "composite": True,
                        "description": "Check the demo thing works",
                    }
                },
            ),
            patch("isvtest.catalog.build_label_map", return_value={"DemoComposedCheck": {"demo"}}),
            patch("isvtest.catalog.build_test_id_map", return_value={"DemoComposedCheck": {"SEC07-01"}}),
            patch("isvtest.catalog.load_released_test_filter", return_value=None),
        ):
            catalog = build_catalog()

        assert catalog == [
            {
                "name": "DemoComposedCheck",
                "description": "Check the demo thing works",
                "labels": ["demo"],
                "test_ids": ["SEC07-01"],
                "source": "isvtest.core.composite",
                "suite": "demo",
                "capability": None,
                "requires": [],
            }
        ]

    def test_composite_is_release_gated_by_name(self) -> None:
        """A composite name is not in the manifest, so it ships unreleased."""
        with (
            patch("isvtest.catalog.discover_all_tests", return_value=[ExplicitLabelCatalogCheck]),
            patch(
                "isvtest.catalog._build_suite_map",
                return_value={
                    "DemoComposedCheck": {
                        "suite": "demo",
                        "capability": None,
                        "requires": [],
                        "composite": True,
                        "description": "Check the demo thing works",
                    }
                },
            ),
            patch("isvtest.catalog.build_label_map", return_value={}),
            patch("isvtest.catalog.build_test_id_map", return_value={}),
            patch("isvtest.catalog.load_released_test_filter", return_value={"StepSuccessCheck"}),
        ):
            assert build_catalog() == []

    def test_sources_are_valid_python_paths(self) -> None:
        """Source paths remain useful implementation metadata, not a suite axis."""
        catalog = build_catalog()
        for entry in catalog:
            assert "." in entry["source"]
            assert entry["source"].startswith("isvtest.")


class TestGetCatalogVersion:
    """Tests for get_catalog_version function."""

    def test_returns_string(self) -> None:
        """Test that get_catalog_version returns a string."""
        version = get_catalog_version()
        assert isinstance(version, str)
        assert len(version) > 0

    def test_returns_dev_when_not_installed(self) -> None:
        """Test that 'dev' is returned when package is not installed."""
        from importlib.metadata import PackageNotFoundError

        with patch(
            "isvreporter.version.version",
            side_effect=PackageNotFoundError("isvtest"),
        ):
            assert get_catalog_version() == "dev"

    def test_the_checkout_never_changes_the_catalog_version(self) -> None:
        """The catalog version is the release number, drift or no drift.

        Whether the build has moved past that release is a separate fact, and
        it is settled by :func:`catalog_digest` comparing the checks this build
        holds against the ones the release published - not by decorating the
        version string, which every consumer is entitled to read plainly.
        """
        from isvreporter.version import describe_checkout

        describe_checkout.cache_clear()
        try:
            with patch("isvreporter.version._repository_root", return_value=Path("/repo")):
                with patch(
                    "subprocess.run",
                    return_value=subprocess.CompletedProcess(
                        args=[], returncode=0, stdout="v0.9.0-3-g08339c7\n", stderr=""
                    ),
                ):
                    with patch("isvreporter.version.version", return_value="0.9.0"):
                        assert get_catalog_version() == "0.9.0"
        finally:
            describe_checkout.cache_clear()


class TestCatalogDocumentDigest:
    """The envelope carries the number the verdict turns on."""

    def test_the_document_carries_the_digest_of_its_own_entries(self) -> None:
        """So the saved artifact shows what the service will compare against.

        Diagnosing a run called off-release means reading the digest somewhere;
        computing it only in passing on the way to the upload left the operator
        with nothing on disk to look at.
        """
        entries = [{"name": "GpuCheck"}]
        with patch("isvtest.catalog.load_released_tests", return_value={"GpuCheck"}):
            document = catalog_document(entries, "1.2.3")
            assert document["catalogDigest"] == catalog_digest(entries)

    def test_the_document_digest_is_what_the_reporter_sends(self) -> None:
        """One number, read from one place, rather than two that ought to agree."""
        from isvctl.reporting import _catalog_digest_of

        with patch("isvtest.catalog.load_released_tests", return_value={"GpuCheck"}):
            document = catalog_document([{"name": "GpuCheck"}], "1.2.3")
        assert _catalog_digest_of(document) == document["catalogDigest"]

    def test_a_document_without_a_digest_reports_none(self) -> None:
        """An older artifact, or one whose release manifest could not be read."""
        from isvctl.reporting import _catalog_digest_of

        assert _catalog_digest_of({"entries": []}) is None
        assert _catalog_digest_of(None) is None


class TestCatalogDigest:
    """The build's own account of which checks it contains."""

    def test_identical_name_sets_digest_identically(self) -> None:
        """Order and duplicates must not matter; the set of names is the fact."""
        one = [{"name": "BmGpuCheck"}, {"name": "K8sNodeCountCheck"}]
        other = [{"name": "K8sNodeCountCheck"}, {"name": "BmGpuCheck"}, {"name": "BmGpuCheck"}]
        with patch(
            "isvtest.catalog.load_released_tests",
            return_value={"BmGpuCheck", "K8sNodeCountCheck"},
        ):
            assert catalog_digest(one) == catalog_digest(other)

    def test_a_renamed_check_changes_the_digest(self) -> None:
        """The lab-42 signature: a build claiming 0.9.0 while running 0.10.0's names."""
        released = {"BmGpuCheck", "GpuCheck"}
        with patch("isvtest.catalog.load_released_tests", return_value=released):
            before = catalog_digest([{"name": "GpuCheck"}])
            after = catalog_digest([{"name": "BmGpuCheck"}])
        assert before != after

    def test_only_names_are_digested(self) -> None:
        """Descriptions and labels churn constantly and are not what results match on."""
        with patch("isvtest.catalog.load_released_tests", return_value={"GpuCheck"}):
            plain = catalog_digest([{"name": "GpuCheck"}])
            decorated = catalog_digest([{"name": "GpuCheck", "description": "rewritten", "labels": ["gpu"]}])
        assert plain == decorated

    def test_unreleased_tests_do_not_read_as_drift(self) -> None:
        """Rafay runs with ISVTEST_INCLUDE_UNRELEASED, and is not thereby off-release.

        build_catalog() honours that variable, so the entries handed here can
        include tests no release published. A published catalog holds a
        release's released checks, so digesting what the operator chose to run
        would report every such partner as running a build that is not the
        release.
        """
        with patch("isvtest.catalog.load_released_tests", return_value={"GpuCheck"}):
            released_only = catalog_digest([{"name": "GpuCheck"}])
            with_unreleased = catalog_digest([{"name": "GpuCheck"}, {"name": "BrandNewCheck"}])
        assert released_only == with_unreleased

    def test_declines_to_digest_when_the_manifest_is_unreadable(self) -> None:
        """Digesting an unfiltered catalog would report a genuine release as drift."""
        with patch("isvtest.catalog.load_released_tests", side_effect=OSError("gone")):
            assert catalog_digest([{"name": "GpuCheck"}]) is None

    def test_matches_the_digest_the_service_computes_for_the_same_names(self) -> None:
        """Pinned to a literal, because this is a wire contract, not an implementation.

        The service applies the same rule to the entry names of a published
        catalog and compares. A change here that its counterpart in
        ``CatalogDigestTest`` does not also make is a change that makes every
        client's digest disagree with every catalog's.
        """
        with patch(
            "isvtest.catalog.load_released_tests",
            return_value={"BmGpuCheck", "K8sNodeCountCheck"},
        ):
            digest = catalog_digest([{"name": "BmGpuCheck"}, {"name": "K8sNodeCountCheck"}])
        assert digest == "sha256:3e45280c8827ebf2aa21f07c78a6c8ba3d442be3d78aeaa4c3dcdcf645b37013"

    def test_is_the_shape_the_service_column_holds(self) -> None:
        with patch("isvtest.catalog.load_released_tests", return_value={"GpuCheck"}):
            digest = catalog_digest([{"name": "GpuCheck"}])
        assert digest.startswith("sha256:")
        assert len(digest) == 71
