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

"""Load the platform's ``StorageProvider`` from a Python file on disk.

The loader imports it, calls the factory, and validates the result.
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path

from isvtest.core.storage_provider.api import StorageProvider


class ShimLoadError(Exception):
    """The shim file could not be loaded or did not implement the contract."""


def _factory_accepts_attributes(factory: Callable[..., object]) -> bool:
    """True when ``build_api`` declares an ``attributes`` keyword (or ``**kwargs``).

    Lets the loader pass manifest ``attributes`` to shims that opt in while
    keeping the documented no-arg ``build_api()`` contract working for the rest.
    """
    try:
        params = inspect.signature(factory).parameters
    except (TypeError, ValueError):
        return False
    if "attributes" in params:
        return True
    return any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())


def build_api_from_path(
    path: str | Path,
    attributes: Mapping[str, str] | None = None,
) -> StorageProvider:
    """Load ``path`` as a Python module, call its ``build_api()``, return the ``StorageProvider``.

    ``path`` is resolved against the current working directory if
    relative; the caller is responsible for resolving against a
    manifest-relative directory before calling.

    ``attributes`` carries the provider's manifest ``attributes`` block. It is
    forwarded as ``build_api(attributes=...)`` only when the shim's factory
    opts in (declares an ``attributes`` keyword or ``**kwargs``); no-arg
    factories keep working unchanged.

    Raises ``ShimLoadError`` when the file is missing, has no
    ``build_api`` callable, or returns something that isn't a
    ``StorageProvider`` subclass.
    """
    shim_path = Path(path).resolve()
    if not shim_path.is_file():
        raise ShimLoadError(f"shim file not found: {shim_path}")

    # Unique module name keeps multiple shims (or repeated loads in tests)
    # from clobbering each other in ``sys.modules``.
    module_name = f"_isvtest_shim_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, shim_path)
    if spec is None or spec.loader is None:
        raise ShimLoadError(f"cannot create import spec for {shim_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(module_name, None)
        raise ShimLoadError(f"failed to import shim {shim_path}: {exc}") from exc

    factory = getattr(module, "build_api", None)
    if not callable(factory):
        raise ShimLoadError(f"shim {shim_path} has no module-level build_api() callable")

    try:
        if _factory_accepts_attributes(factory):
            api = factory(attributes=dict(attributes or {}))
        else:
            api = factory()
    except Exception as exc:
        raise ShimLoadError(f"build_api() in {shim_path} raised: {exc}") from exc

    if not isinstance(api, StorageProvider):
        raise ShimLoadError(
            f"build_api() in {shim_path} returned {type(api).__name__}, expected a StorageProvider subclass"
        )
    return api
