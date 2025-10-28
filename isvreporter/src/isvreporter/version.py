"""Version detection utilities.

Version resolution works as follows:

1. CI/CD build: The GitLab pipeline generates `_version.py` files with the
   release version (e.g., `__version__ = "dev-abc1234"`). These files are
   baked into the wheel and take priority at runtime.

   See `.gitlab-ci.yml` build-wheels job:
       echo "__version__ = \"dev-${NEXT_VERSION}\"" > <package>/src/<package>/_version.py

2. Local development: If `_version.py` doesn't exist, we try to get the
   current git SHA for a meaningful dev version (e.g., `dev-c42ee70`).

3. Fallback: If git isn't available, we use `dev-local`.

Note: `_version.py` files are in `.gitignore` and should never be committed.
"""

import importlib
import subprocess


def get_version(package_name: str) -> str:
    """Get package version with fallback chain.

    Args:
        package_name: Name of the package (e.g., 'isvctl', 'isvtest', 'isvreporter')

    Returns:
        Version string (e.g., 'dev-abc1234', 'dev-c42ee70', or 'dev-local')
    """
    # CI/CD baked version
    try:
        version_module = importlib.import_module(f"{package_name}._version")
        return version_module.__version__
    except (ModuleNotFoundError, AttributeError):
        # Fall back to git/local when the baked version module is missing
        pass

    # Local dev: try git SHA
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return f"dev-{result.stdout.strip()}"
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        # Fall back to dev-local if git is unavailable or too slow
        pass

    return "dev-local"
