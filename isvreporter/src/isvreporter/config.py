"""Configuration constants for ISV Lab Service."""

import os
from pathlib import Path

# Staging environment
STG_ISV_LAB_SERVICE_ENDPOINT = "https://stg-api.ncp-isv-validation-labs.nvidia.com"
STG_ISV_SSA_ISSUER = "https://x0mdb040zusoe-hsewurjcwnwm8q004e27d8nschkbm.stg.ssa.nvidia.com"

# Production environment (public-api is accessible from ISV clusters)
PROD_ISV_LAB_SERVICE_ENDPOINT = "https://public-api.ncp-isv-validation-labs.nvidia.com"
PROD_ISV_SSA_ISSUER = "https://qqs53u3y8cuxje91j1ow9o9krteb6dzw0qrruchzxaa.ssa.nvidia.com"


def is_dev_mode() -> bool:
    """Detect if running in development mode (from source) vs installed wheel.

    Dev mode is detected when:
    - ISV_ENV=staging is explicitly set, OR
    - Running from source (path contains 'src/isvreporter')

    Production mode when:
    - ISV_ENV=production is explicitly set, OR
    - Running from installed wheel (site-packages)
    """
    # Explicit override via environment variable
    env = os.environ.get("ISV_ENV", "").lower()
    if env == "staging":
        return True
    if env == "production":
        return False

    # Auto-detect based on installation path
    # Dev mode: running from source (e.g., /path/to/nv-isv-tools/isvreporter/src/isvreporter)
    # Prod mode: installed wheel (e.g., .../site-packages/isvreporter)
    config_path = Path(__file__).resolve()
    return "src/isvreporter" in str(config_path)


def get_default_endpoint() -> str:
    """Get the default ISV Lab Service endpoint based on environment."""
    return STG_ISV_LAB_SERVICE_ENDPOINT if is_dev_mode() else PROD_ISV_LAB_SERVICE_ENDPOINT


def get_default_ssa_issuer() -> str:
    """Get the default SSA issuer based on environment."""
    return STG_ISV_SSA_ISSUER if is_dev_mode() else PROD_ISV_SSA_ISSUER


# Defaults (auto-detected based on dev/prod mode)
DEFAULT_ISV_LAB_SERVICE_ENDPOINT = get_default_endpoint()
DEFAULT_ISV_SSA_ISSUER = get_default_ssa_issuer()
