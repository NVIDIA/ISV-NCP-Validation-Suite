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

"""Unit tests for ``isvtest.core.storage.load_provider_registry``."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from isvtest.core.storage import (
    ManifestError,
    Provider,
    load_provider_registry,
)
from isvtest.core.storage_provider import MockStorageApi, StorageProvider

_MOCK_SHIM_BODY = (
    "from isvtest.core.storage_provider import MockStorageApi\n"
    "def build_api():\n"
    "    return MockStorageApi(tenant_id='reg-test')\n"
)


def _write_manifest(path: Path, payload: dict) -> Path:
    path.write_text(yaml.safe_dump(payload, sort_keys=False))
    return path


def _shim_provider(name: str = "p1", module: str = "shim.py", **extra) -> dict:
    entry = {
        "name": name,
        "type": "file",
        "tenant_id": "tenant-1",
        "shim": {"kind": "python", "module": module},
    }
    entry.update(extra)
    return entry


class TestLoadProviderRegistry:
    def test_empty_manifest_path_returns_empty_list(self) -> None:
        assert load_provider_registry({}) == []
        assert load_provider_registry({"manifest_path": ""}) == []
        assert load_provider_registry({"manifest_path": "   "}) == []

    def test_missing_manifest_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ManifestError, match="not found"):
            load_provider_registry({"manifest_path": str(tmp_path / "missing.yaml")})

    def test_malformed_yaml_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.yaml"
        path.write_text("schema_version: v1alpha2\nproviders: [unterminated\n")
        with pytest.raises(ManifestError, match="failed to parse"):
            load_provider_registry({"manifest_path": str(path)})

    def test_unsupported_schema_version_raises(self, tmp_path: Path) -> None:
        path = _write_manifest(tmp_path / "m.yaml", {"schema_version": "v0", "providers": []})
        with pytest.raises(ManifestError, match="schema_version"):
            load_provider_registry({"manifest_path": str(path)})

    def test_providers_must_be_list(self, tmp_path: Path) -> None:
        path = _write_manifest(tmp_path / "m.yaml", {"schema_version": "v1alpha2", "providers": {}})
        with pytest.raises(ManifestError, match="providers must be a list"):
            load_provider_registry({"manifest_path": str(path)})

    def test_python_shim_is_loaded(self, tmp_path: Path) -> None:
        (tmp_path / "shim.py").write_text(_MOCK_SHIM_BODY)
        path = _write_manifest(
            tmp_path / "m.yaml",
            {"schema_version": "v1alpha2", "providers": [_shim_provider()]},
        )
        providers = load_provider_registry({"manifest_path": str(path)})
        assert len(providers) == 1
        provider = providers[0]
        assert isinstance(provider, Provider)
        assert provider.name == "p1"
        assert provider.volume_type == "file"
        assert provider.tenant_id == "tenant-1"
        assert provider.has_shim is True
        assert isinstance(provider.api, StorageProvider)
        assert isinstance(provider.api, MockStorageApi)

    def test_rest_shim_kind_returns_provider_without_api(self, tmp_path: Path) -> None:
        path = _write_manifest(
            tmp_path / "m.yaml",
            {
                "schema_version": "v1alpha2",
                "providers": [
                    {
                        "name": "rest-only",
                        "type": "file",
                        "tenant_id": "t-rest",
                        "shim": {"kind": "rest", "endpoint": "https://example.com"},
                    }
                ],
            },
        )
        providers = load_provider_registry({"manifest_path": str(path)})
        assert len(providers) == 1
        assert providers[0].shim_kind == "rest"
        assert providers[0].api is None
        assert providers[0].has_shim is False

    def test_provider_without_shim_has_no_api(self, tmp_path: Path) -> None:
        # A provider with no `shim:` block (e.g. CSI-only, not yet onboarded) is
        # carried through with no api; StorageProviderApiCheck skips it. Extra
        # vendor keys the loader does not consume are ignored harmlessly.
        path = _write_manifest(
            tmp_path / "m.yaml",
            {
                "schema_version": "v1alpha2",
                "providers": [
                    {
                        "name": "ebs",
                        "type": "block",
                        "tenant_id": "123456789012",
                        "csi": {"provisioner": "ebs.csi.aws.com", "storage_classes": ["gp3"]},
                    }
                ],
            },
        )
        providers = load_provider_registry({"manifest_path": str(path)})
        assert providers[0].shim_kind is None
        assert providers[0].api is None
        assert providers[0].has_shim is False

    def test_multi_provider_manifest_preserves_order(self, tmp_path: Path) -> None:
        (tmp_path / "shim.py").write_text(_MOCK_SHIM_BODY)
        path = _write_manifest(
            tmp_path / "m.yaml",
            {
                "schema_version": "v1alpha2",
                "providers": [
                    _shim_provider(name="alpha"),
                    {"name": "beta", "type": "block", "tenant_id": "t"},
                    _shim_provider(name="gamma"),
                ],
            },
        )
        providers = load_provider_registry({"manifest_path": str(path)})
        assert [p.name for p in providers] == ["alpha", "beta", "gamma"]
        assert [p.has_shim for p in providers] == [True, False, True]

    def test_duplicate_provider_name_raises(self, tmp_path: Path) -> None:
        (tmp_path / "shim.py").write_text(_MOCK_SHIM_BODY)
        path = _write_manifest(
            tmp_path / "m.yaml",
            {
                "schema_version": "v1alpha2",
                "providers": [_shim_provider(name="dup"), _shim_provider(name="dup")],
            },
        )
        with pytest.raises(ManifestError, match="duplicate"):
            load_provider_registry({"manifest_path": str(path)})

    def test_missing_provider_name_raises(self, tmp_path: Path) -> None:
        path = _write_manifest(
            tmp_path / "m.yaml",
            {"schema_version": "v1alpha2", "providers": [{"type": "file"}]},
        )
        with pytest.raises(ManifestError, match=r"name .*is required"):
            load_provider_registry({"manifest_path": str(path)})

    def test_invalid_provider_type_raises(self, tmp_path: Path) -> None:
        path = _write_manifest(
            tmp_path / "m.yaml",
            {"schema_version": "v1alpha2", "providers": [{"name": "p", "type": "object"}]},
        )
        with pytest.raises(ManifestError, match="type must be"):
            load_provider_registry({"manifest_path": str(path)})

    def test_shim_module_resolved_relative_to_manifest_dir(self, tmp_path: Path) -> None:
        sub = tmp_path / "shims"
        sub.mkdir()
        (sub / "api.py").write_text(_MOCK_SHIM_BODY)
        path = _write_manifest(
            tmp_path / "m.yaml",
            {
                "schema_version": "v1alpha2",
                "providers": [_shim_provider(module="shims/api.py")],
            },
        )
        providers = load_provider_registry({"manifest_path": str(path)})
        assert providers[0].has_shim is True

    def test_shim_load_failure_wrapped_as_manifest_error(self, tmp_path: Path) -> None:
        (tmp_path / "broken.py").write_text("raise SyntaxError('nope')\n")
        path = _write_manifest(
            tmp_path / "m.yaml",
            {"schema_version": "v1alpha2", "providers": [_shim_provider(module="broken.py")]},
        )
        with pytest.raises(ManifestError, match="failed to load shim"):
            load_provider_registry({"manifest_path": str(path)})

    def test_invalid_capability_state_raises(self, tmp_path: Path) -> None:
        (tmp_path / "shim.py").write_text(_MOCK_SHIM_BODY)
        path = _write_manifest(
            tmp_path / "m.yaml",
            {
                "schema_version": "v1alpha2",
                "providers": [_shim_provider(capabilities={"volumeManagement": "yes"})],
            },
        )
        with pytest.raises(ManifestError, match="capability state must be one of"):
            load_provider_registry({"manifest_path": str(path)})

    def test_attributes_are_string_coerced(self, tmp_path: Path) -> None:
        (tmp_path / "shim.py").write_text(_MOCK_SHIM_BODY)
        path = _write_manifest(
            tmp_path / "m.yaml",
            {
                "schema_version": "v1alpha2",
                "providers": [_shim_provider(attributes={"region": "us-east-1", "count": 3})],
            },
        )
        providers = load_provider_registry({"manifest_path": str(path)})
        assert providers[0].attributes == {"region": "us-east-1", "count": "3"}

    def test_integer_tenant_id_is_string_coerced(self, tmp_path: Path) -> None:
        path = _write_manifest(
            tmp_path / "m.yaml",
            {
                "schema_version": "v1alpha2",
                "providers": [{"name": "aws", "type": "block", "tenant_id": 123456789012}],
            },
        )
        providers = load_provider_registry({"manifest_path": str(path)})
        assert providers[0].tenant_id == "123456789012"

    def test_unsupported_shim_kind_raises(self, tmp_path: Path) -> None:
        path = _write_manifest(
            tmp_path / "m.yaml",
            {
                "schema_version": "v1alpha2",
                "providers": [{"name": "weird", "type": "file", "shim": {"kind": "binary", "module": "x"}}],
            },
        )
        with pytest.raises(ManifestError, match=r"shim.kind"):
            load_provider_registry({"manifest_path": str(path)})

    def test_python_shim_requires_module(self, tmp_path: Path) -> None:
        path = _write_manifest(
            tmp_path / "m.yaml",
            {
                "schema_version": "v1alpha2",
                "providers": [{"name": "p", "type": "file", "shim": {"kind": "python"}}],
            },
        )
        with pytest.raises(ManifestError, match=r"shim.module is required"):
            load_provider_registry({"manifest_path": str(path)})


class TestIdentityAndCapabilities:
    def test_name_and_type_derived_from_provider_block(self, tmp_path: Path) -> None:
        path = _write_manifest(
            tmp_path / "m.yaml",
            {
                "schema_version": "v1alpha2",
                "namespace": "aws.amazon.com",
                "providers": [
                    {
                        "id": "fsx-lustre",
                        "provider": {"type": "FILE", "protocols": ["lustre"], "version": "0.1.0"},
                        "tenant_id": "123456789012",
                    }
                ],
            },
        )
        provider = load_provider_registry({"manifest_path": str(path)})[0]
        assert provider.name == "fsx-lustre"
        assert provider.volume_type == "file"
        assert provider.provider_namespace == "aws.amazon.com"
        assert provider.provider_id == "fsx-lustre"
        assert provider.provider_version == "0.1.0"
        assert provider.storage_protocols == ("lustre",)

    def test_explicit_name_type_win_over_provider_block(self, tmp_path: Path) -> None:
        path = _write_manifest(
            tmp_path / "m.yaml",
            {
                "schema_version": "v1alpha2",
                "providers": [
                    {
                        "name": "explicit-name",
                        "type": "block",
                        "id": "other",
                        "provider": {"type": "file"},
                    }
                ],
            },
        )
        providers = load_provider_registry({"manifest_path": str(path)})
        assert providers[0].name == "explicit-name"
        assert providers[0].volume_type == "block"

    def test_legacy_identity_block_is_fallback(self, tmp_path: Path) -> None:
        path = _write_manifest(
            tmp_path / "m.yaml",
            {
                "schema_version": "v1alpha2",
                "providers": [
                    {
                        "identity": {
                            "provider": {"domain": "aws.amazon.com", "id": "fsx", "version": "0.2.0"},
                            "storage_type": "FILE",
                            "storage_protocol": "lustre",
                        },
                        "tenant_id": "1",
                    }
                ],
            },
        )
        provider = load_provider_registry({"manifest_path": str(path)})[0]
        assert provider.name == "fsx"
        assert provider.volume_type == "file"
        assert provider.provider_namespace == "aws.amazon.com"
        assert provider.storage_protocols == ("lustre",)
        assert provider.provider_version == "0.2.0"

    def test_missing_name_and_id_raises(self, tmp_path: Path) -> None:
        path = _write_manifest(
            tmp_path / "m.yaml",
            {"schema_version": "v1alpha2", "providers": [{"provider": {"type": "file"}}]},
        )
        with pytest.raises(ManifestError, match=r"name .*is required"):
            load_provider_registry({"manifest_path": str(path)})

    def test_hierarchical_capabilities_lowered_to_cap_ids(self, tmp_path: Path) -> None:
        path = _write_manifest(
            tmp_path / "m.yaml",
            {
                "schema_version": "v1alpha2",
                "providers": [
                    {
                        "name": "p",
                        "type": "file",
                        "capabilities": {
                            "tenantManagement": {"list": "none", "get": "none", "getQuota": "native"},
                            "volumeManagement": "native",
                            "quotaManagement": "none",
                        },
                    }
                ],
            },
        )
        caps = load_provider_registry({"manifest_path": str(path)})[0].expected_capabilities
        assert caps["tenant.list"] is False
        assert caps["tenant.getQuota"] is True
        assert caps["volume.create"] is True
        assert caps["volume.list"] is True
        assert caps["quota.directory.set"] is False
        assert caps["quota.user.get"] is False

    def test_package_default_capabilities_apply(self, tmp_path: Path) -> None:
        path = _write_manifest(
            tmp_path / "m.yaml",
            {
                "schema_version": "v1alpha2",
                "default_capabilities": {"default": "none"},
                "providers": [{"name": "p", "type": "file", "capabilities": {"volumeManagement": "native"}}],
            },
        )
        caps = load_provider_registry({"manifest_path": str(path)})[0].expected_capabilities
        # volume.* native via provider block; everything else falls to package default none.
        assert caps["volume.create"] is True
        assert caps["quota.user.set"] is False
        assert caps["tenant.list"] is False

    def test_package_default_capabilities_camelcase_key(self, tmp_path: Path) -> None:
        # The camelCase `defaultCapabilities` key mirrors the upstream package
        # manifest and resolves identically to the snake_case alias.
        path = _write_manifest(
            tmp_path / "m.yaml",
            {
                "schema_version": "v1alpha2",
                "defaultCapabilities": {"default": "none"},
                "providers": [{"name": "p", "type": "file", "capabilities": {"volumeManagement": "native"}}],
            },
        )
        caps = load_provider_registry({"manifest_path": str(path)})[0].expected_capabilities
        assert caps["volume.create"] is True
        assert caps["quota.user.set"] is False
        assert caps["tenant.list"] is False

    def test_no_capabilities_leaves_map_empty(self, tmp_path: Path) -> None:
        path = _write_manifest(
            tmp_path / "m.yaml",
            {"schema_version": "v1alpha2", "providers": [{"name": "p", "type": "file"}]},
        )
        provider = load_provider_registry({"manifest_path": str(path)})[0]
        assert provider.expected_capabilities == {}

    def test_capability_qualifiers_parsed(self, tmp_path: Path) -> None:
        path = _write_manifest(
            tmp_path / "m.yaml",
            {
                "schema_version": "v1alpha2",
                "providers": [
                    {
                        "name": "p",
                        "type": "file",
                        "capability_qualifiers": {"quota.directory": {"idAssignment": "backend"}},
                    }
                ],
            },
        )
        provider = load_provider_registry({"manifest_path": str(path)})[0]
        assert provider.capability_qualifiers == {"quota.directory": {"idAssignment": "backend"}}

    def test_unconsumed_sections_are_ignored(self, tmp_path: Path) -> None:
        # csi / topology / protocol_expectations are no longer part of the
        # manifest contract (the CSI/NFS/POSIX checks are config-driven). Any
        # such leftover keys are ignored harmlessly rather than rejected.
        path = _write_manifest(
            tmp_path / "m.yaml",
            {
                "schema_version": "v1alpha2",
                "providers": [
                    {
                        "name": "p",
                        "type": "file",
                        "csi": {"storage_classes_by_type": {"shared_fs": "sc"}},
                        "topology": {"node_selector": {"k": "v"}},
                        "protocol_expectations": {"nfs": {"version": "3"}},
                    }
                ],
            },
        )
        providers = load_provider_registry({"manifest_path": str(path)})
        assert providers[0].name == "p"
        assert not hasattr(providers[0], "csi")

    def test_v1alpha1_manifest_has_empty_capabilities(self, tmp_path: Path) -> None:
        path = _write_manifest(
            tmp_path / "m.yaml",
            {
                "schema_version": "v1alpha1",
                "providers": [{"name": "p", "type": "file", "tenant_id": "t"}],
            },
        )
        provider = load_provider_registry({"manifest_path": str(path)})[0]
        assert provider.expected_capabilities == {}


class TestInstanceConfig:
    """The optional second layer: a per-instance ``config.yaml`` overlaying the
    manifest's defaultTenant / storageClasses / capabilities (consume-only)."""

    def _manifest(self, tmp_path: Path) -> Path:
        return _write_manifest(
            tmp_path / "m.yaml",
            {
                "schema_version": "v1alpha2",
                "providers": [
                    {
                        "name": "p",
                        "type": "file",
                        "tenant_id": "manifest-tenant",
                        "capabilities": {
                            "volumeManagement": "native",
                            "tenantManagement": {"getQuota": "native"},
                        },
                    }
                ],
            },
        )

    def test_no_sibling_config_leaves_manifest_untouched(self, tmp_path: Path) -> None:
        path = self._manifest(tmp_path)
        provider = load_provider_registry({"manifest_path": str(path)})[0]
        assert provider.tenant_id == "manifest-tenant"
        assert provider.expected_capabilities["volume.create"] is True
        assert provider.storage_classes == ()

    def test_sibling_config_overrides_tenant_and_capabilities(self, tmp_path: Path) -> None:
        path = self._manifest(tmp_path)
        _write_manifest(
            tmp_path / "config.yaml",
            {
                "schema_version": "v1alpha1",
                "instance": {
                    "id": "default",
                    "provider": {
                        "defaultTenant": "instance-tenant",
                        "storageClasses": ["sc-fast", "sc-bulk"],
                        # disable a manifest-native leaf; enable a group.
                        "capabilities": {"volume.create": "disabled"},
                    },
                },
            },
        )
        provider = load_provider_registry({"manifest_path": str(path)})[0]
        assert provider.tenant_id == "instance-tenant"
        assert provider.storage_classes == ("sc-fast", "sc-bulk")
        # volume.create disabled by the instance; volume.list still native.
        assert provider.expected_capabilities["volume.create"] is False
        assert provider.expected_capabilities["volume.list"] is True

    def test_group_override_expands_to_leaves(self, tmp_path: Path) -> None:
        path = self._manifest(tmp_path)
        _write_manifest(
            tmp_path / "config.yaml",
            {
                "schema_version": "v1alpha1",
                "instance": {"provider": {"capabilities": {"volume": "disabled"}}},
            },
        )
        caps = load_provider_registry({"manifest_path": str(path)})[0].expected_capabilities
        assert caps["volume.list"] is False
        assert caps["volume.get"] is False
        assert caps["volume.create"] is False
        assert caps["volume.delete"] is False

    def test_enable_adds_undeclared_capability(self, tmp_path: Path) -> None:
        path = self._manifest(tmp_path)
        _write_manifest(
            tmp_path / "config.yaml",
            {
                "schema_version": "v1alpha1",
                "instance": {"provider": {"capabilities": {"tenant.list": "enabled"}}},
            },
        )
        caps = load_provider_registry({"manifest_path": str(path)})[0].expected_capabilities
        # tenant.list was undeclared (unchecked) in the manifest; the instance
        # enables it, so it becomes an expected-supported surface.
        assert caps["tenant.list"] is True

    def test_explicit_instance_config_path(self, tmp_path: Path) -> None:
        path = self._manifest(tmp_path)
        inst = _write_manifest(
            tmp_path / "elsewhere.yaml",
            {
                "schema_version": "v1alpha1",
                "instance": {"provider": {"defaultTenant": "explicit-tenant"}},
            },
        )
        provider = load_provider_registry({"manifest_path": str(path), "instance_config_path": str(inst)})[0]
        assert provider.tenant_id == "explicit-tenant"

    def test_missing_explicit_instance_config_raises(self, tmp_path: Path) -> None:
        path = self._manifest(tmp_path)
        with pytest.raises(ManifestError, match="instance config file not found"):
            load_provider_registry({"manifest_path": str(path), "instance_config_path": str(tmp_path / "nope.yaml")})

    def test_bool_override_value_accepted(self, tmp_path: Path) -> None:
        path = self._manifest(tmp_path)
        _write_manifest(
            tmp_path / "config.yaml",
            {
                "schema_version": "v1alpha1",
                "instance": {"provider": {"capabilities": {"volume.create": False}}},
            },
        )
        caps = load_provider_registry({"manifest_path": str(path)})[0].expected_capabilities
        assert caps["volume.create"] is False

    def test_unknown_capability_key_raises(self, tmp_path: Path) -> None:
        path = self._manifest(tmp_path)
        _write_manifest(
            tmp_path / "config.yaml",
            {
                "schema_version": "v1alpha1",
                "instance": {"provider": {"capabilities": {"bogus.surface": "enabled"}}},
            },
        )
        with pytest.raises(ManifestError, match="unknown capability key"):
            load_provider_registry({"manifest_path": str(path)})

    def test_bad_override_value_raises(self, tmp_path: Path) -> None:
        path = self._manifest(tmp_path)
        _write_manifest(
            tmp_path / "config.yaml",
            {
                "schema_version": "v1alpha1",
                "instance": {"provider": {"capabilities": {"volume.create": "on"}}},
            },
        )
        with pytest.raises(ManifestError, match="must be 'enabled' or 'disabled'"):
            load_provider_registry({"manifest_path": str(path)})
