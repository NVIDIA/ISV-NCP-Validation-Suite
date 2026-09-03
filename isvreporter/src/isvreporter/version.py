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

"""Version resolution for all workspace packages.

The canonical version lives in each package's pyproject.toml. At runtime,
importlib.metadata reads it from installed package metadata (works in wheels,
editable installs, and airgapped environments after ``uv sync``).

That number alone is only trustworthy on a release tag. A checkout taken
between releases still carries the previous bump's version, so a tree several
commits past ``v0.9.0`` reports ``0.9.0`` while running checks that release
never had - results then get scored against a catalog that does not describe
them. When this code is running from a git checkout the tag is therefore
consulted directly and the distance from it travels in a PEP 440 suffix
(``0.9.0.post3+g08339c7``), which the service reads as "no published catalog
describes this build".
"""

import logging
import re
import subprocess
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

logger = logging.getLogger(__name__)

# --long so a tagged commit still reports its distance (0) rather than a bare
# tag, which keeps one output shape to parse. --match so a tag that is not a
# release marker cannot become the version.
_DESCRIBE_COMMAND = (
    "git",
    "describe",
    "--tags",
    "--long",
    "--dirty",
    "--match",
    "v*",
)

_DESCRIBE_PATTERN = re.compile(r"^v(?P<tag>.+)-(?P<distance>\d+)-g(?P<commit>[0-9a-f]+)(?P<dirty>-dirty)?$")

# A hung git call must not hold up a test run that is otherwise ready to report.
_DESCRIBE_TIMEOUT_SECONDS = 5

# Where this module sits in the workspace tree. A repository that does not hold
# the file at this path is somebody else's checkout, whatever its tags say.
_SOURCE_RELATIVE_PATH = Path("isvreporter/src/isvreporter/version.py")


def _repository_root() -> Path | None:
    """Return the git checkout this module lives in, or None when installed.

    Only this workspace's own tree counts. Creating an environment inside
    another repository is ordinary - ``uv sync`` puts ``.venv`` under whatever
    tree it is run from, and ``--target`` installs anywhere at all - and a
    ``v*`` tag there describes cleanly enough to be taken for ours, which would
    report a partner's version for our checks. An editable install still
    counts, because its files stay in the source tree.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        # A worktree records .git as a file, so existence is the test, not is_dir.
        if (parent / ".git").exists():
            return parent if here == parent / _SOURCE_RELATIVE_PATH else None
    return None


@lru_cache(maxsize=1)
def describe_checkout() -> str | None:
    """Return the version this checkout is really at, or None when not in one.

    The workspace releases its packages in lockstep off a single repository tag,
    so one description covers all of them. Returns the bare tag on a clean
    tagged commit, and otherwise appends the distance and commit
    (``0.9.0.post3+g08339c7``, plus ``.dirty`` for uncommitted changes).

    Cached: the answer cannot change within a process, and every package's
    version lookup would otherwise spawn its own git.
    """
    root = _repository_root()
    if root is None:
        return None

    try:
        completed = subprocess.run(
            _DESCRIBE_COMMAND,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=_DESCRIBE_TIMEOUT_SECONDS,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        # No git binary, no tags, a shallow clone: all leave the metadata
        # version as the best available answer, none is worth failing a run for.
        logger.debug("Could not describe the checkout at %s: %s", root, exc)
        return None

    match = _DESCRIBE_PATTERN.match(completed.stdout.strip())
    if match is None:
        logger.debug("Unexpected git describe output: %r", completed.stdout.strip())
        return None

    tag = match["tag"]
    distance = int(match["distance"])
    if distance == 0 and not match["dirty"]:
        return tag

    local = f"g{match['commit']}" + (".dirty" if match["dirty"] else "")
    return f"{tag}.post{distance}+{local}"


def get_version(package_name: str) -> str:
    """Return the version of *package_name*, or ``"dev"`` if unavailable.

    In a git checkout the tag wins over the installed metadata. It is the more
    accurate of the two: metadata is written at install time and goes stale the
    moment the tree moves, whether by pulling past a release or by pulling to
    one without re-syncing.

    Args:
        package_name: Distribution name (e.g. ``"isvreporter"``).

    Returns:
        Version string such as ``"1.2.3"`` or ``"0.9.0.post3+g08339c7"``.
    """
    described = describe_checkout()
    if described is not None:
        return described

    try:
        return version(package_name)
    except PackageNotFoundError:
        return "dev"


def is_released_version(candidate: str) -> bool:
    """Whether *candidate* names a release rather than a build between releases.

    Mirrors the service's own rule, so the client can warn about a version the
    service is about to treat as having no published catalog.
    """
    return re.fullmatch(r"\d+(\.\d+)*((a|b|rc)\d+)?", candidate.strip()) is not None
