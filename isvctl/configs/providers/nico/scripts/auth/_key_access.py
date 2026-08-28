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

"""Provision and remove a throwaway specified key on a NICo site (AUTH-XX-03).

AUTH-XX-03 needs an SSH key synced to the site to evidence key-based
serial-console access. Sites do not always have one, so query_key_access.py
mints an ephemeral key, observes the access path it unlocks, and removes it
again -- all inside one process, so the key cannot outlive the run.

``provision`` records every ID it creates into the caller's ``ThrowawayKey`` as
it goes, including on a mid-provision failure, so the caller's ``finally`` can
always clean up what was actually created.

The matching private key is generated in a temp dir and discarded immediately;
only the public half is registered, so the credential is unusable by anyone
even in the window before it is removed.

NICo API endpoints used (``/carbide/`` segment, like the other NICo scripts):
  POST   /{org}/carbide/sshkey
  POST   /{org}/carbide/sshkeygroup
  GET    /{org}/carbide/sshkeygroup/{id}        (poll for sync)
  DELETE /{org}/carbide/sshkeygroup/{id}, /{org}/carbide/sshkey/{id}
  PATCH  /{org}/carbide/site/{site_id}          (best-effort; older API only)
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from common.nico_client import (
    delete_if_present,
    forge_get,
    forge_patch,
    forge_post,
    sshkeygroup_synced_to_site,
)

SYNC_POLL_TIMEOUT_SECONDS = 180
SYNC_POLL_INTERVAL_SECONDS = 5


@dataclass
class ThrowawayKey:
    """IDs created while provisioning, and the site state to restore on removal."""

    sshkey_id: str = ""
    sshkeygroup_id: str = ""
    synced: bool = False
    # Prior site isSerialConsoleSSHKeysEnabled value, or None when we did not flip it.
    restore_ssh_keys_enabled: bool | None = None

    def __bool__(self) -> bool:
        """True when something was created that removal has to clean up."""
        return bool(self.sshkey_id or self.sshkeygroup_id or self.restore_ssh_keys_enabled is not None)


def _generate_public_key(comment: str) -> str:
    """Generate an ed25519 keypair and return only the public key.

    The private key lives in a temp dir that is removed on return, so the
    registered public key has no usable counterpart.
    """
    with tempfile.TemporaryDirectory() as tmp:
        key_path = os.path.join(tmp, "id_ed25519")
        subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-N", "", "-C", comment, "-f", key_path, "-q"],
            check=True,
            capture_output=True,
        )
        return Path(f"{key_path}.pub").read_text().strip()


def _wait_for_sync(org: str, group_id: str, site_id: str, token: str, *, base_url: str) -> bool:
    """Poll the key group until it is synced to the site or the timeout elapses."""
    if not group_id:
        # No group id means nothing to poll (the create response had no id).
        return False
    deadline = time.monotonic() + SYNC_POLL_TIMEOUT_SECONDS
    while True:
        group = forge_get(org, f"sshkeygroup/{group_id}", token, base_url=base_url)
        if sshkeygroup_synced_to_site(group, site_id):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(SYNC_POLL_INTERVAL_SECONDS)


def provision(*, org: str, site_id: str, api_base: str, token: str, created: ThrowawayKey) -> None:
    """Create a throwaway key group synced to the site, recording IDs in ``created``.

    Raises on failure. ``created`` carries whatever was created before the
    failure so the caller can still remove it.
    """
    name = f"isvtest-auth-xx-03-{uuid.uuid4().hex[:8]}"

    key = forge_post(
        org, "sshkey", token, base_url=api_base, body={"name": name, "publicKey": _generate_public_key(name)}
    )
    created.sshkey_id = key.get("id") or ""
    # remove() skips a resource with no id, so continuing here would strand the
    # key on the org for good -- the leak this whole flow exists to avoid.
    if not created.sshkey_id:
        raise RuntimeError(f"NICo sshkey create returned no id for {name}")

    group = forge_post(
        org,
        "sshkeygroup",
        token,
        base_url=api_base,
        body={"name": name, "sshKeyIds": [created.sshkey_id], "siteIds": [site_id]},
    )
    created.sshkeygroup_id = group.get("id") or ""
    if not created.sshkeygroup_id:
        raise RuntimeError(f"NICo sshkeygroup create returned no id for {name}")

    created.synced = _wait_for_sync(org, created.sshkeygroup_id, site_id, token, base_url=api_base)
    if not created.synced:
        return

    # Older clusters gate SSH-key SOL access on a tenant-settable site flag; newer
    # ones derive it from key-group sync (the flag is deprecated and the PATCH may
    # be rejected). Enabling it is therefore best-effort: only record a restore
    # value when we actually flipped it off->on.
    site = forge_get(org, f"site/{site_id}", token, base_url=api_base)
    if not site.get("isSerialConsoleSSHKeysEnabled"):
        try:
            forge_patch(org, f"site/{site_id}", token, base_url=api_base, body={"isSerialConsoleSSHKeysEnabled": True})
            created.restore_ssh_keys_enabled = False
        except Exception:
            # Deprecated/derived on this API version; nothing to restore.
            pass


def remove(*, org: str, site_id: str, api_base: str, token: str, created: ThrowawayKey) -> list[str]:
    """Remove what ``provision`` created; return a list of cleanup failures.

    A failure on one resource does not stop the others, so a single stuck
    resource cannot strand the rest.
    """
    errors: list[str] = []

    # Delete the group before the key: deleting the group removes the key's
    # group membership, so the key can then be deleted on its own.
    for resource, resource_id in (("sshkeygroup", created.sshkeygroup_id), ("sshkey", created.sshkey_id)):
        if not resource_id:
            continue
        try:
            delete_if_present(org, f"{resource}/{resource_id}", token, base_url=api_base)
        except Exception as e:
            errors.append(f"{resource} {resource_id}: {type(e).__name__}: {e}")

    if created.restore_ssh_keys_enabled is not None:
        try:
            forge_patch(
                org,
                f"site/{site_id}",
                token,
                base_url=api_base,
                body={"isSerialConsoleSSHKeysEnabled": created.restore_ssh_keys_enabled},
            )
        except Exception as e:
            errors.append(f"restore site flag: {type(e).__name__}: {e}")

    return errors
