"""Version resolution for all workspace packages.

The canonical version lives in each package's pyproject.toml. At runtime,
importlib.metadata reads it from installed package metadata (works in wheels,
editable installs, and airgapped environments after ``uv sync``).
"""

from importlib.metadata import PackageNotFoundError, version


def get_version(package_name: str) -> str:
    """Return the installed version of *package_name*, or ``"dev"`` if unavailable.

    Args:
        package_name: Distribution name (e.g. ``"isvreporter"``).

    Returns:
        Version string such as ``"1.2.3"`` or ``"dev"``.
    """
    try:
        return version(package_name)
    except PackageNotFoundError:
        return "dev"
