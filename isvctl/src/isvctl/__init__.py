"""ISV Lab controller for cluster lifecycle orchestration.

This package provides the `isvctl` CLI tool for orchestrating the full ISV
validation loop: cluster creation, test execution, and teardown.
"""

from isvreporter.version import get_version

__version__ = get_version("isvctl")
