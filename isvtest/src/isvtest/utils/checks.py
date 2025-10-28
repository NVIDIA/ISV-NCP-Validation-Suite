"""Common utility functions for validation checks."""

import shutil
from pathlib import Path


def stub_exists(stub_path: str) -> bool:
    """Check if a stub script exists and is a file.

    Args:
        stub_path: Path to the stub script (relative or absolute).

    Returns:
        True if the stub exists and is a file, False otherwise.
    """
    path = Path(stub_path)
    return path.exists() and path.is_file()


def command_exists(command: str) -> bool:
    """Check if a command is available in PATH.

    Args:
        command: Name of the command to check (e.g., 'kubectl', 'sinfo').

    Returns:
        True if the command is available, False otherwise.
    """
    return shutil.which(command) is not None
