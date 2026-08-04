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

"""Hermetic tests for the VAST storage provider shim."""

from __future__ import annotations

import importlib.util
import io
import urllib.error
from pathlib import Path
from typing import Any

import pytest

from isvtest.core.storage_provider import (
    DeleteUserQuotaRequest,
    QuotaLimits,
    SetUserQuotaRequest,
    StorageApiError,
    UserQuota,
)

_SHIM = (
    Path(__file__).resolve().parents[2]
    / "isvctl"
    / "configs"
    / "providers"
    / "vast"
    / "scripts"
    / "storage"
    / "vast"
    / "api.py"
)


def _load_shim():
    """Load the VAST shim by path, matching manifest-loader behavior."""
    spec = importlib.util.spec_from_file_location("vast_api_under_test", _SHIM)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


vast = _load_shim()


def _api():
    """Build a VAST API instance without making backend calls."""
    return vast.VastApi(endpoint="https://vast.invalid", token="token", tenant="tenant", storage_path="/exports/k8s")


def test_http_endpoint_is_rejected_before_auth_headers_are_sent():
    """Reject cleartext VMS endpoints during client construction."""
    with pytest.raises(StorageApiError, match="https://"):
        vast.VastApi(endpoint="http://vast.invalid", token="token", storage_path="/exports/k8s")


def test_user_quota_set_sends_inode_limits_for_default_and_override():
    """Write hard_limit_inodes wherever quota.user advertises inode support."""
    api = _api()
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def _request(method: str, path: str, *, body=None, **_kwargs):
        calls.append((method, path, body))
        if method == "GET" and path == "/api/quotas/123/":
            return {"id": 123, "is_user_quota": True}
        return {"id": 123}

    api._request = _request  # type: ignore[method-assign]
    api.get_user_quota = lambda req: UserQuota(  # type: ignore[method-assign]
        tenant_id=req.tenant_id or "", volume_id=req.volume_id, user=req.user
    )

    api.set_user_quota(
        SetUserQuotaRequest(
            UserQuota(tenant_id="tenant", volume_id="123", user=None, hard=QuotaLimits(bytes=4096, inodes=25))
        )
    )
    api.set_user_quota(
        SetUserQuotaRequest(
            UserQuota(tenant_id="tenant", volume_id="123", user="1000", hard=QuotaLimits(bytes=8192, inodes=50))
        )
    )

    default_body = calls[0][2]
    override_body = calls[-1][2]
    assert default_body == {
        "is_user_quota": True,
        "default_user_quota": {"hard_limit": 4096, "hard_limit_inodes": 25},
    }
    assert override_body is not None
    assert override_body["hard_limit_inodes"] == 50


def test_default_user_quota_delete_clears_inode_limit_too():
    """Clear default-user byte and inode limits together."""
    api = _api()
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def _request(method: str, path: str, *, body=None, **_kwargs):
        calls.append((method, path, body))
        return {}

    api._request = _request  # type: ignore[method-assign]
    api.delete_user_quota(DeleteUserQuotaRequest(tenant_id="tenant", volume_id="123", user=None))
    assert calls == [
        ("PATCH", "/api/quotas/123/", {"default_user_quota": {"hard_limit": None, "hard_limit_inodes": None}})
    ]


def test_http_errors_do_not_surface_raw_response_bodies(monkeypatch):
    """Keep backend response bodies out of raised validation errors."""
    api = _api()

    def _boom(*_args, **_kwargs):
        raise urllib.error.HTTPError(
            url="https://vast.invalid/api/quotas/",
            code=500,
            msg="Internal Server Error",
            hdrs={},
            fp=io.BytesIO(b'{"token":"secret-token"}'),
        )

    monkeypatch.setattr(vast.urllib.request, "urlopen", _boom)
    with pytest.raises(StorageApiError) as excinfo:
        api._request("GET", "/api/quotas/")
    assert "HTTP 500 Internal Server Error" in str(excinfo.value)
    assert "secret-token" not in str(excinfo.value)
