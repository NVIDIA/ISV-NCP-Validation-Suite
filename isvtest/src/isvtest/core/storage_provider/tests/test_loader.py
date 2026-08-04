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

"""Unit tests for ``isvtest.core.storage_provider.loader.build_api_from_path``."""

from __future__ import annotations

from pathlib import Path

import pytest

from isvtest.core.storage_provider import (
    MockStorageApi,
    ShimLoadError,
    StorageProvider,
    build_api_from_path,
)


def _write_shim(tmp_path: Path, body: str, filename: str = "api.py") -> Path:
    """Write a temporary shim module for loader tests."""
    shim = tmp_path / filename
    shim.write_text(body)
    return shim


class TestBuildApiFromPath:
    """Tests for BuildApiFromPath."""

    def test_loads_mock_storage_api(self, tmp_path: Path) -> None:
        """Verify loads mock storage api."""
        shim = _write_shim(
            tmp_path,
            "from isvtest.core.storage_provider import MockStorageApi\n"
            "def build_api():\n"
            "    return MockStorageApi(tenant_id='unit-test')\n",
        )
        api = build_api_from_path(shim)
        assert isinstance(api, StorageProvider)
        assert isinstance(api, MockStorageApi)
        api.health_check()

    def test_missing_file_raises_shim_load_error(self, tmp_path: Path) -> None:
        """Verify missing file raises shim load error."""
        with pytest.raises(ShimLoadError, match="not found"):
            build_api_from_path(tmp_path / "nope.py")

    def test_missing_build_api_callable_raises(self, tmp_path: Path) -> None:
        """Verify missing build api callable raises."""
        shim = _write_shim(tmp_path, "x = 1\n")
        with pytest.raises(ShimLoadError, match="build_api"):
            build_api_from_path(shim)

    def test_non_storageapi_return_raises(self, tmp_path: Path) -> None:
        """Verify non storageapi return raises."""
        shim = _write_shim(
            tmp_path,
            "def build_api():\n    return object()\n",
        )
        with pytest.raises(ShimLoadError, match="expected a StorageProvider subclass"):
            build_api_from_path(shim)

    def test_build_api_exception_is_wrapped(self, tmp_path: Path) -> None:
        """Verify build api exception is wrapped."""
        shim = _write_shim(
            tmp_path,
            "def build_api():\n    raise RuntimeError('boom')\n",
        )
        with pytest.raises(ShimLoadError, match="boom"):
            build_api_from_path(shim)

    def test_module_import_exception_is_wrapped(self, tmp_path: Path) -> None:
        """Verify module import exception is wrapped."""
        shim = _write_shim(tmp_path, "raise ImportError('cannot import')\n")
        with pytest.raises(ShimLoadError, match="cannot import"):
            build_api_from_path(shim)

    def test_repeated_loads_get_independent_modules(self, tmp_path: Path) -> None:
        """Verify repeated loads get independent modules."""
        shim = _write_shim(
            tmp_path,
            "from isvtest.core.storage_provider import MockStorageApi\ndef build_api():\n    return MockStorageApi()\n",
        )
        api_a = build_api_from_path(shim)
        api_b = build_api_from_path(shim)
        assert api_a is not api_b

    def test_attributes_forwarded_when_factory_opts_in(self, tmp_path: Path) -> None:
        """Verify attributes forwarded when factory opts in."""
        shim = _write_shim(
            tmp_path,
            "from isvtest.core.storage_provider import MockStorageApi\n"
            "def build_api(attributes=None):\n"
            "    return MockStorageApi(tenant_id=(attributes or {}).get('tenant', 'fallback'))\n",
        )
        api = build_api_from_path(shim, attributes={"tenant": "from-manifest"})
        assert api._default_tenant == "from-manifest"

    def test_attributes_ignored_for_no_arg_factory(self, tmp_path: Path) -> None:
        """Verify attributes ignored for no arg factory."""
        shim = _write_shim(
            tmp_path,
            "from isvtest.core.storage_provider import MockStorageApi\n"
            "def build_api():\n    return MockStorageApi(tenant_id='no-arg')\n",
        )
        api = build_api_from_path(shim, attributes={"tenant": "ignored"})
        assert api._default_tenant == "no-arg"
