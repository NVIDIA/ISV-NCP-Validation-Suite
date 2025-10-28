"""ISV Lab Test Results Reporter - report validation test results to ISV Lab Service."""

from isvreporter.config import (
    DEFAULT_ISV_LAB_SERVICE_ENDPOINT,
    DEFAULT_ISV_SSA_ISSUER,
    PROD_ISV_LAB_SERVICE_ENDPOINT,
    PROD_ISV_SSA_ISSUER,
    STG_ISV_LAB_SERVICE_ENDPOINT,
    STG_ISV_SSA_ISSUER,
    get_default_endpoint,
    get_default_ssa_issuer,
    is_dev_mode,
)
from isvreporter.version import get_version

__all__ = [
    "DEFAULT_ISV_LAB_SERVICE_ENDPOINT",
    "DEFAULT_ISV_SSA_ISSUER",
    "PROD_ISV_LAB_SERVICE_ENDPOINT",
    "PROD_ISV_SSA_ISSUER",
    "STG_ISV_LAB_SERVICE_ENDPOINT",
    "STG_ISV_SSA_ISSUER",
    "__version__",
    "get_default_endpoint",
    "get_default_ssa_issuer",
    "is_dev_mode",
]

__version__ = get_version("isvreporter")
