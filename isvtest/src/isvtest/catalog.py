"""Test catalog generation for coverage tracking.

Builds a structured catalog of all available validation tests by calling
discover_all_tests() and serializing each BaseValidation subclass's metadata.
The catalog is version-keyed by the installed isvtest package version.
"""

import logging
from typing import Any

from isvreporter.version import get_version

from isvtest.core.discovery import discover_all_tests

logger = logging.getLogger(__name__)


def build_catalog() -> list[dict[str, Any]]:
    """Discover all validation tests and return structured catalog entries.

    Returns:
        List of catalog entry dicts, each containing:
            - name: Validation class name (e.g. "K8sNodeCountCheck")
            - description: Human-readable description from class metadata
            - markers: List of marker strings (e.g. ["kubernetes", "gpu"])
            - module: Fully qualified module path (e.g. "isvtest.validations.k8s_nodes")
    """
    catalog: list[dict[str, Any]] = []
    seen: set[str] = set()

    for cls in discover_all_tests():
        name = cls.__name__
        if name in seen:
            continue
        seen.add(name)

        catalog.append(
            {
                "name": name,
                "description": getattr(cls, "description", "") or "",
                "markers": list(getattr(cls, "markers", [])),
                "module": cls.__module__,
            }
        )

    logger.info("Built test catalog with %d entries", len(catalog))
    return catalog


def get_catalog_version() -> str:
    """Return the installed isvtest package version.

    Returns:
        Version string (e.g. "1.2.3") or "dev" if not installed as a package.
    """
    return get_version("isvtest")
