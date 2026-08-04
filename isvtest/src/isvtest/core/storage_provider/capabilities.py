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

"""Typed capability tree + composition, mirroring nv-storage's ``capabilities.py``.

Trimmed to the singular capability ids this suite models (no batch surfaces).
The registry ids, qualifier vocabulary, and the ``Capability`` wire record live
in :mod:`isvtest.core.storage_provider.api`; this module layers on:

* ``_compose_capabilities`` / ``_narrow_states`` - the deploy-time / runtime
  composition ``new_implementation()`` sits on;
* the typed, navigable read tree a consumer walks (``Capabilities``) and the
  write view an author refines in ``capability_qualifiers`` (``ImplementationCapabilities``).

A semantic fact set on a group inherits to its leaves: the group views expose
the inherited getters/setters, and the per-leaf views expose each leaf's
*effective* (own + inherited) qualifiers, settable as a leaf override.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import cast

from isvtest.core.storage_provider.api import (
    CAP_DIRECTORY_QUOTA_DELETE,
    CAP_DIRECTORY_QUOTA_GET,
    CAP_DIRECTORY_QUOTA_LIST,
    CAP_DIRECTORY_QUOTA_SET,
    CAP_GROUP_QUOTA,
    CAP_GROUP_TENANT,
    CAP_GROUP_VOLUME,
    CAP_TENANT_GET,
    CAP_TENANT_GET_QUOTA,
    CAP_TENANT_LIST,
    CAP_TENANT_LIST_QUOTAS,
    CAP_USER_QUOTA_DELETE,
    CAP_USER_QUOTA_GET,
    CAP_USER_QUOTA_LIST,
    CAP_USER_QUOTA_SET,
    CAP_VOLUME_CREATE,
    CAP_VOLUME_DELETE,
    CAP_VOLUME_GET,
    CAP_VOLUME_LIST,
    CAPABILITY_IDS,
    QUAL_ACCOUNTING,
    QUAL_BYTE_GRANULARITY,
    QUAL_DEFAULT_USER_SLOT,
    QUAL_ID_ASSIGNMENT,
    QUAL_INODES,
    QUAL_MULTI_PATH_BINDING,
    QUAL_MULTI_TENANT,
    QUAL_TIERED,
    Capability,
    CapabilityState,
    IDAssignment,
    QuotaAccounting,
    _resolve_qualifiers,
)

__all__ = [
    "Capabilities",
    "CapabilityNode",
    "ImplementationCapabilities",
    "ImplementationNode",
]


def _resolve_override(overrides: Mapping[str, bool], cap_id: str) -> bool | None:
    """Most-specific config override for ``cap_id``: exact id, then group prefixes.

    Walks ``"quota.user.set"`` -> ``"quota.user"`` -> ``"quota"`` and returns the
    first match, so a leaf override beats the group it sits under. ``None`` = no
    override touches this id.
    """
    key = cap_id
    while True:
        if key in overrides:
            return overrides[key]
        dot = key.rfind(".")
        if dot < 0:
            return None
        key = key[:dot]


def _compose_capabilities(
    declared: list[Capability],
    overrides: Mapping[str, bool],
    qualifiers: Mapping[str, Mapping[str, str]],
) -> list[Capability]:
    """Resolve the ADVERTISED capability list from the declared core.

    For each declared surface: a config override may flip ``supported`` <->
    ``disabled`` (by id or group prefix) but can NOT resurrect a surface the code
    left ``unimplemented``; qualifiers from the hook are merged on top of any the
    surface already carries (hook wins). A pure function (no I/O).
    """
    result: list[Capability] = []
    for cap in declared:
        state = cap.state
        override = _resolve_override(overrides, cap.id)
        if override is False and state == "supported":
            state = "disabled"
        elif override is True and state == "disabled":
            state = "supported"
        if state == "unimplemented":
            result.append(replace(cap, state=state, qualifiers={}))
            continue
        merged = {**cap.qualifiers, **_resolve_qualifiers(qualifiers, cap.id)}
        result.append(replace(cap, state=state, qualifiers=merged))
    return result


#: Roll-up / fold order, most-available first.
_STATE_ORDER: tuple[CapabilityState, ...] = (
    "supported",
    "unavailable",
    "disabled",
    "unimplemented",
)
_STATE_RANK = {s: i for i, s in enumerate(_STATE_ORDER)}


def _leaves_under(prefix: str) -> list[str]:
    """Registry leaf ids at or beneath a node id (the whole tree for the root)."""
    if prefix == "":
        return list(CAPABILITY_IDS)
    return [cid for cid in CAPABILITY_IDS if cid == prefix or cid.startswith(prefix + ".")]


def _child_id(prefix: str, seg: str) -> str:
    return seg if prefix == "" else f"{prefix}.{seg}"


def _resolve_state(states: Mapping[str, CapabilityState], cap_id: str) -> CapabilityState | None:
    """Most-specific runtime-state override for ``cap_id`` (exact id, then groups)."""
    key = cap_id
    while True:
        if key in states:
            return states[key]
        dot = key.rfind(".")
        if dot < 0:
            return None
        key = key[:dot]


def _narrow_states(caps: list[Capability], states: Mapping[str, CapabilityState]) -> list[Capability]:
    """Fold the hook's runtime-availability states into the advertised list.

    A state set on a leaf (or a group, fanning down) is applied only when it is
    MORE restrictive than the surface's current state - so the hook can take a
    served surface ``unavailable`` / ``disabled`` but never re-enable one config
    or the missing implementation left off.
    """
    if not states:
        return caps
    out: list[Capability] = []
    for cap in caps:
        want = _resolve_state(states, cap.id)
        cur = cap.state or "unimplemented"
        if want is not None and _STATE_RANK.get(want, 99) > _STATE_RANK.get(cur, 99):
            out.append(replace(cap, state=want))
        else:
            out.append(cap)
    return out


# --- typed capability tree (read) --------------------------------------------


class CapabilityNode:
    """A positioned node (group or leaf) in the advertised capability tree.

    Backed by the flat advertised ``Capability`` list: a leaf reads its own
    effective state and qualifiers; a group rolls its leaves up (supported if any
    leaf is, else the most-available state) and recovers a group-wide qualifier
    from a representative leaf.
    """

    __slots__ = ("_by_id", "_id")

    def __init__(self, by_id: Mapping[str, Capability], node_id: str) -> None:
        self._by_id = by_id
        self._id = node_id

    @property
    def id(self) -> str:
        """The node's dotted registry id (``""`` for the root)."""
        return self._id

    def state(self) -> CapabilityState:
        """The node's effective state (a group rolls up the most-available leaf)."""
        cap = self._by_id.get(self._id)
        if cap is not None:
            return cap.state if cap.state is not None else "unimplemented"
        present = {self._by_id[lid].state for lid in _leaves_under(self._id) if lid in self._by_id}
        for s in _STATE_ORDER:
            if s in present:
                return s
        return "unimplemented"

    def is_supported(self) -> bool:
        """Whether the node is serviceable here and now."""
        return self.state() == "supported"

    def qualifiers(self) -> dict[str, str]:
        """The node-scoped resolved qualifier bag (a representative leaf's, for a group)."""
        cap = self._by_id.get(self._id)
        if cap is not None:
            return dict(cap.qualifiers)
        for leaf in _leaves_under(self._id):
            if leaf in self._by_id:
                return dict(self._by_id[leaf].qualifiers)
        return {}

    def _qual(self, key: str) -> str | None:
        for leaf in _leaves_under(self._id):
            cap = self._by_id.get(leaf)
            if cap is not None and key in cap.qualifiers:
                return cap.qualifiers[key]
        return None

    def _bool(self, key: str, default: bool) -> bool:
        v = self._qual(key)
        return v == "true" if v is not None else default

    def _int(self, key: str, default: int) -> int:
        v = self._qual(key)
        if v is not None:
            try:
                return int(v)
            except ValueError:
                pass
        return default

    def _child(self, seg: str) -> CapabilityNode:
        return CapabilityNode(self._by_id, _child_id(self._id, seg))


class TenantLeafCaps(CapabilityNode):
    """Read view of a ``tenant`` leaf - its effective qualifiers."""

    def multi_tenant(self) -> bool:
        return self._bool(QUAL_MULTI_TENANT, False)

    def tiered(self) -> bool:
        return self._bool(QUAL_TIERED, False)


class DirectoryQuotaLeafCaps(CapabilityNode):
    """Read view of a ``quota.directory`` leaf - its effective qualifiers."""

    def byte_granularity(self) -> int:
        return self._int(QUAL_BYTE_GRANULARITY, 1)

    def inodes(self) -> bool:
        return self._bool(QUAL_INODES, True)

    def id_assignment(self) -> IDAssignment | None:
        return cast("IDAssignment | None", self._qual(QUAL_ID_ASSIGNMENT))

    def multi_path_binding(self) -> bool:
        return self._bool(QUAL_MULTI_PATH_BINDING, False)

    def accounting(self) -> QuotaAccounting | None:
        return cast("QuotaAccounting | None", self._qual(QUAL_ACCOUNTING))


class UserQuotaLeafCaps(CapabilityNode):
    """Read view of a ``quota.user`` leaf - its effective qualifiers."""

    def byte_granularity(self) -> int:
        return self._int(QUAL_BYTE_GRANULARITY, 1)

    def inodes(self) -> bool:
        return self._bool(QUAL_INODES, True)

    def id_assignment(self) -> IDAssignment | None:
        return cast("IDAssignment | None", self._qual(QUAL_ID_ASSIGNMENT))

    def default_user_slot(self) -> bool:
        return self._bool(QUAL_DEFAULT_USER_SLOT, True)


class TenantCaps(CapabilityNode):
    """Read view of the ``tenant`` group."""

    def list(self) -> TenantLeafCaps:
        return TenantLeafCaps(self._by_id, _child_id(self._id, "list"))

    def get(self) -> TenantLeafCaps:
        return TenantLeafCaps(self._by_id, _child_id(self._id, "get"))

    def get_quota(self) -> TenantLeafCaps:
        return TenantLeafCaps(self._by_id, _child_id(self._id, "getQuota"))

    def list_quotas(self) -> TenantLeafCaps:
        return TenantLeafCaps(self._by_id, _child_id(self._id, "listQuotas"))

    def multi_tenant(self) -> bool:
        return self._bool(QUAL_MULTI_TENANT, False)

    def tiered(self) -> bool:
        return self._bool(QUAL_TIERED, False)


class VolumeCaps(CapabilityNode):
    """Read view of the ``volume`` group (no typed qualifiers)."""

    def list(self) -> CapabilityNode:
        return self._child("list")

    def get(self) -> CapabilityNode:
        return self._child("get")

    def create(self) -> CapabilityNode:
        return self._child("create")

    def delete(self) -> CapabilityNode:
        return self._child("delete")


class QuotaCaps(CapabilityNode):
    """Read view of the ``quota`` group."""

    def directory(self) -> DirectoryQuotaCaps:
        return DirectoryQuotaCaps(self._by_id, _child_id(self._id, "directory"))

    def user(self) -> UserQuotaCaps:
        return UserQuotaCaps(self._by_id, _child_id(self._id, "user"))

    def byte_granularity(self) -> int:
        return self._int(QUAL_BYTE_GRANULARITY, 1)

    def inodes(self) -> bool:
        return self._bool(QUAL_INODES, True)

    def id_assignment(self) -> IDAssignment | None:
        return cast("IDAssignment | None", self._qual(QUAL_ID_ASSIGNMENT))


class DirectoryQuotaCaps(CapabilityNode):
    """Read view of the ``quota.directory`` group."""

    def list(self) -> DirectoryQuotaLeafCaps:
        return DirectoryQuotaLeafCaps(self._by_id, _child_id(self._id, "list"))

    def get(self) -> DirectoryQuotaLeafCaps:
        return DirectoryQuotaLeafCaps(self._by_id, _child_id(self._id, "get"))

    def set(self) -> DirectoryQuotaLeafCaps:
        return DirectoryQuotaLeafCaps(self._by_id, _child_id(self._id, "set"))

    def delete(self) -> DirectoryQuotaLeafCaps:
        return DirectoryQuotaLeafCaps(self._by_id, _child_id(self._id, "delete"))

    def byte_granularity(self) -> int:
        return self._int(QUAL_BYTE_GRANULARITY, 1)

    def inodes(self) -> bool:
        return self._bool(QUAL_INODES, True)

    def id_assignment(self) -> IDAssignment | None:
        return cast("IDAssignment | None", self._qual(QUAL_ID_ASSIGNMENT))

    def multi_path_binding(self) -> bool:
        return self._bool(QUAL_MULTI_PATH_BINDING, False)

    def accounting(self) -> QuotaAccounting | None:
        return cast("QuotaAccounting | None", self._qual(QUAL_ACCOUNTING))


class UserQuotaCaps(CapabilityNode):
    """Read view of the ``quota.user`` group."""

    def list(self) -> UserQuotaLeafCaps:
        return UserQuotaLeafCaps(self._by_id, _child_id(self._id, "list"))

    def get(self) -> UserQuotaLeafCaps:
        return UserQuotaLeafCaps(self._by_id, _child_id(self._id, "get"))

    def set(self) -> UserQuotaLeafCaps:
        return UserQuotaLeafCaps(self._by_id, _child_id(self._id, "set"))

    def delete(self) -> UserQuotaLeafCaps:
        return UserQuotaLeafCaps(self._by_id, _child_id(self._id, "delete"))

    def byte_granularity(self) -> int:
        return self._int(QUAL_BYTE_GRANULARITY, 1)

    def inodes(self) -> bool:
        return self._bool(QUAL_INODES, True)

    def id_assignment(self) -> IDAssignment | None:
        return cast("IDAssignment | None", self._qual(QUAL_ID_ASSIGNMENT))

    def default_user_slot(self) -> bool:
        return self._bool(QUAL_DEFAULT_USER_SLOT, True)


class Capabilities(CapabilityNode):
    """The typed, navigable read view of a provider's advertised capability tree.

    Navigate to a group or straight to a leaf, then read a node's ``state`` /
    ``is_supported`` and its typed qualifiers. Rebuilt from the advertised list
    each call (retain it if you read repeatedly).
    """

    def raw_list(self) -> list[Capability]:
        """The verbatim flat records this tree was built from - the wire form."""
        return list(self._by_id.values())

    def effective_list(self) -> list[Capability]:
        """Every registry leaf with its folded effective state and resolved qualifiers."""
        return [
            Capability(
                id=cid,
                state=CapabilityNode(self._by_id, cid).state(),
                qualifiers=CapabilityNode(self._by_id, cid).qualifiers(),
            )
            for cid in CAPABILITY_IDS
        ]

    def tenant(self) -> TenantCaps:
        return TenantCaps(self._by_id, CAP_GROUP_TENANT)

    def volume(self) -> VolumeCaps:
        return VolumeCaps(self._by_id, CAP_GROUP_VOLUME)

    def quota(self) -> QuotaCaps:
        return QuotaCaps(self._by_id, CAP_GROUP_QUOTA)

    def list_tenants(self) -> TenantLeafCaps:
        return TenantLeafCaps(self._by_id, CAP_TENANT_LIST)

    def get_tenant(self) -> TenantLeafCaps:
        return TenantLeafCaps(self._by_id, CAP_TENANT_GET)

    def get_tenant_quota(self) -> TenantLeafCaps:
        return TenantLeafCaps(self._by_id, CAP_TENANT_GET_QUOTA)

    def list_tenant_quotas(self) -> TenantLeafCaps:
        return TenantLeafCaps(self._by_id, CAP_TENANT_LIST_QUOTAS)

    def list_volumes(self) -> CapabilityNode:
        return CapabilityNode(self._by_id, CAP_VOLUME_LIST)

    def get_volume(self) -> CapabilityNode:
        return CapabilityNode(self._by_id, CAP_VOLUME_GET)

    def create_volume(self) -> CapabilityNode:
        return CapabilityNode(self._by_id, CAP_VOLUME_CREATE)

    def delete_volume(self) -> CapabilityNode:
        return CapabilityNode(self._by_id, CAP_VOLUME_DELETE)

    def list_directory_quotas(self) -> DirectoryQuotaLeafCaps:
        return DirectoryQuotaLeafCaps(self._by_id, CAP_DIRECTORY_QUOTA_LIST)

    def get_directory_quota(self) -> DirectoryQuotaLeafCaps:
        return DirectoryQuotaLeafCaps(self._by_id, CAP_DIRECTORY_QUOTA_GET)

    def set_directory_quota(self) -> DirectoryQuotaLeafCaps:
        return DirectoryQuotaLeafCaps(self._by_id, CAP_DIRECTORY_QUOTA_SET)

    def delete_directory_quota(self) -> DirectoryQuotaLeafCaps:
        return DirectoryQuotaLeafCaps(self._by_id, CAP_DIRECTORY_QUOTA_DELETE)

    def list_user_quotas(self) -> UserQuotaLeafCaps:
        return UserQuotaLeafCaps(self._by_id, CAP_USER_QUOTA_LIST)

    def get_user_quota(self) -> UserQuotaLeafCaps:
        return UserQuotaLeafCaps(self._by_id, CAP_USER_QUOTA_GET)

    def set_user_quota(self) -> UserQuotaLeafCaps:
        return UserQuotaLeafCaps(self._by_id, CAP_USER_QUOTA_SET)

    def delete_user_quota(self) -> UserQuotaLeafCaps:
        return UserQuotaLeafCaps(self._by_id, CAP_USER_QUOTA_DELETE)


def _new_capabilities(caps: list[Capability]) -> Capabilities:
    """Build the typed read tree over an advertised ``Capability`` list."""
    return Capabilities({cap.id: cap for cap in caps}, "")


# --- typed capability tree (author write view) -------------------------------


class ImplementationNode:
    """A positioned node of the writable author view.

    ``set_state`` feeds the node's runtime-availability (a group fans down to its
    leaves); the SDK folds it with detection + config so an author can narrow a
    surface (``"unavailable"`` / ``"disabled"``) but never conjure one the code
    does not serve. ``set_qualifier`` is the node-scoped escape hatch for a
    dynamic qualifier with no typed setter. Both chain (return the node).
    """

    __slots__ = ("_id", "_quals", "_states")

    def __init__(
        self,
        quals: dict[str, dict[str, str]],
        states: dict[str, CapabilityState],
        node_id: str,
    ) -> None:
        self._quals = quals
        self._states = states
        self._id = node_id

    @property
    def id(self) -> str:
        return self._id

    def set_state(self, state: CapabilityState) -> ImplementationNode:
        self._states[self._id] = state
        return self

    def set_qualifier(self, key: str, value: str) -> ImplementationNode:
        self._quals.setdefault(self._id, {})[key] = value
        return self

    def _set(self, key: str, value: str) -> None:
        self._quals.setdefault(self._id, {})[key] = value

    def _child(self, seg: str) -> ImplementationNode:
        return ImplementationNode(self._quals, self._states, _child_id(self._id, seg))


class TenantLeafImplCaps(ImplementationNode):
    """Writable view of a ``tenant`` leaf - a per-leaf qualifier override."""

    def set_multi_tenant(self, v: bool) -> TenantLeafImplCaps:
        self._set(QUAL_MULTI_TENANT, "true" if v else "false")
        return self

    def set_tiered(self, v: bool) -> TenantLeafImplCaps:
        self._set(QUAL_TIERED, "true" if v else "false")
        return self


class DirectoryQuotaLeafImplCaps(ImplementationNode):
    """Writable view of a ``quota.directory`` leaf - a per-leaf qualifier override."""

    def set_byte_granularity(self, v: int) -> DirectoryQuotaLeafImplCaps:
        self._set(QUAL_BYTE_GRANULARITY, str(v))
        return self

    def set_inodes(self, v: bool) -> DirectoryQuotaLeafImplCaps:
        self._set(QUAL_INODES, "true" if v else "false")
        return self

    def set_id_assignment(self, v: IDAssignment) -> DirectoryQuotaLeafImplCaps:
        self._set(QUAL_ID_ASSIGNMENT, v)
        return self

    def set_multi_path_binding(self, v: bool) -> DirectoryQuotaLeafImplCaps:
        self._set(QUAL_MULTI_PATH_BINDING, "true" if v else "false")
        return self

    def set_accounting(self, v: QuotaAccounting) -> DirectoryQuotaLeafImplCaps:
        self._set(QUAL_ACCOUNTING, v)
        return self


class UserQuotaLeafImplCaps(ImplementationNode):
    """Writable view of a ``quota.user`` leaf - a per-leaf qualifier override."""

    def set_byte_granularity(self, v: int) -> UserQuotaLeafImplCaps:
        self._set(QUAL_BYTE_GRANULARITY, str(v))
        return self

    def set_inodes(self, v: bool) -> UserQuotaLeafImplCaps:
        self._set(QUAL_INODES, "true" if v else "false")
        return self

    def set_id_assignment(self, v: IDAssignment) -> UserQuotaLeafImplCaps:
        self._set(QUAL_ID_ASSIGNMENT, v)
        return self

    def set_default_user_slot(self, v: bool) -> UserQuotaLeafImplCaps:
        self._set(QUAL_DEFAULT_USER_SLOT, "true" if v else "false")
        return self


class TenantImplCaps(ImplementationNode):
    """Writable view of the ``tenant`` group."""

    def list(self) -> TenantLeafImplCaps:
        return TenantLeafImplCaps(self._quals, self._states, _child_id(self._id, "list"))

    def get(self) -> TenantLeafImplCaps:
        return TenantLeafImplCaps(self._quals, self._states, _child_id(self._id, "get"))

    def get_quota(self) -> TenantLeafImplCaps:
        return TenantLeafImplCaps(self._quals, self._states, _child_id(self._id, "getQuota"))

    def list_quotas(self) -> TenantLeafImplCaps:
        return TenantLeafImplCaps(self._quals, self._states, _child_id(self._id, "listQuotas"))

    def set_multi_tenant(self, v: bool) -> TenantImplCaps:
        self._set(QUAL_MULTI_TENANT, "true" if v else "false")
        return self

    def set_tiered(self, v: bool) -> TenantImplCaps:
        self._set(QUAL_TIERED, "true" if v else "false")
        return self


class VolumeImplCaps(ImplementationNode):
    """Writable view of the ``volume`` group (no typed qualifiers)."""

    def list(self) -> ImplementationNode:
        return self._child("list")

    def get(self) -> ImplementationNode:
        return self._child("get")

    def create(self) -> ImplementationNode:
        return self._child("create")

    def delete(self) -> ImplementationNode:
        return self._child("delete")


class QuotaImplCaps(ImplementationNode):
    """Writable view of the ``quota`` group."""

    def directory(self) -> DirectoryQuotaImplCaps:
        return DirectoryQuotaImplCaps(self._quals, self._states, _child_id(self._id, "directory"))

    def user(self) -> UserQuotaImplCaps:
        return UserQuotaImplCaps(self._quals, self._states, _child_id(self._id, "user"))

    def set_byte_granularity(self, v: int) -> QuotaImplCaps:
        self._set(QUAL_BYTE_GRANULARITY, str(v))
        return self

    def set_inodes(self, v: bool) -> QuotaImplCaps:
        self._set(QUAL_INODES, "true" if v else "false")
        return self

    def set_id_assignment(self, v: IDAssignment) -> QuotaImplCaps:
        self._set(QUAL_ID_ASSIGNMENT, v)
        return self


class DirectoryQuotaImplCaps(ImplementationNode):
    """Writable view of the ``quota.directory`` group."""

    def list(self) -> DirectoryQuotaLeafImplCaps:
        return DirectoryQuotaLeafImplCaps(self._quals, self._states, _child_id(self._id, "list"))

    def get(self) -> DirectoryQuotaLeafImplCaps:
        return DirectoryQuotaLeafImplCaps(self._quals, self._states, _child_id(self._id, "get"))

    def set(self) -> DirectoryQuotaLeafImplCaps:
        return DirectoryQuotaLeafImplCaps(self._quals, self._states, _child_id(self._id, "set"))

    def delete(self) -> DirectoryQuotaLeafImplCaps:
        return DirectoryQuotaLeafImplCaps(self._quals, self._states, _child_id(self._id, "delete"))

    def set_byte_granularity(self, v: int) -> DirectoryQuotaImplCaps:
        self._set(QUAL_BYTE_GRANULARITY, str(v))
        return self

    def set_inodes(self, v: bool) -> DirectoryQuotaImplCaps:
        self._set(QUAL_INODES, "true" if v else "false")
        return self

    def set_id_assignment(self, v: IDAssignment) -> DirectoryQuotaImplCaps:
        self._set(QUAL_ID_ASSIGNMENT, v)
        return self

    def set_multi_path_binding(self, v: bool) -> DirectoryQuotaImplCaps:
        self._set(QUAL_MULTI_PATH_BINDING, "true" if v else "false")
        return self

    def set_accounting(self, v: QuotaAccounting) -> DirectoryQuotaImplCaps:
        self._set(QUAL_ACCOUNTING, v)
        return self


class UserQuotaImplCaps(ImplementationNode):
    """Writable view of the ``quota.user`` group."""

    def list(self) -> UserQuotaLeafImplCaps:
        return UserQuotaLeafImplCaps(self._quals, self._states, _child_id(self._id, "list"))

    def get(self) -> UserQuotaLeafImplCaps:
        return UserQuotaLeafImplCaps(self._quals, self._states, _child_id(self._id, "get"))

    def set(self) -> UserQuotaLeafImplCaps:
        return UserQuotaLeafImplCaps(self._quals, self._states, _child_id(self._id, "set"))

    def delete(self) -> UserQuotaLeafImplCaps:
        return UserQuotaLeafImplCaps(self._quals, self._states, _child_id(self._id, "delete"))

    def set_byte_granularity(self, v: int) -> UserQuotaImplCaps:
        self._set(QUAL_BYTE_GRANULARITY, str(v))
        return self

    def set_inodes(self, v: bool) -> UserQuotaImplCaps:
        self._set(QUAL_INODES, "true" if v else "false")
        return self

    def set_id_assignment(self, v: IDAssignment) -> UserQuotaImplCaps:
        self._set(QUAL_ID_ASSIGNMENT, v)
        return self

    def set_default_user_slot(self, v: bool) -> UserQuotaImplCaps:
        self._set(QUAL_DEFAULT_USER_SLOT, "true" if v else "false")
        return self


class ImplementationCapabilities(ImplementationNode):
    """The writable view handed to ``capability_qualifiers`` to refine a provider.

    Navigate with the typed group accessors and amend in place with the typed
    setters (a fact set on a group inherits to its leaves), or reach any node by
    dotted id with ``get`` for a dynamic ``set_qualifier`` / ``set_state``.
    """

    def __init__(self) -> None:
        super().__init__({}, {}, "")

    def tenant(self) -> TenantImplCaps:
        return TenantImplCaps(self._quals, self._states, CAP_GROUP_TENANT)

    def volume(self) -> VolumeImplCaps:
        return VolumeImplCaps(self._quals, self._states, CAP_GROUP_VOLUME)

    def quota(self) -> QuotaImplCaps:
        return QuotaImplCaps(self._quals, self._states, CAP_GROUP_QUOTA)

    def get(self, cap_id: str) -> ImplementationNode:
        """A node positioned at an arbitrary capability id or dotted group prefix."""
        return ImplementationNode(self._quals, self._states, cap_id)

    def _collected(
        self,
    ) -> tuple[dict[str, dict[str, str]], dict[str, CapabilityState]]:
        """The recorded (qualifier-overrides, runtime-states), keyed by node id."""
        return self._quals, self._states
