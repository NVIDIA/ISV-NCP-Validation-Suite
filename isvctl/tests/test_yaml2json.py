"""Tests for yaml2json.py script."""

import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "yaml2json.py"


def run_yaml2json(yaml_file: str) -> tuple[int, str, str]:
    """Run yaml2json.py and return (exit_code, stdout, stderr)."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), yaml_file],
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


class TestYaml2Json:
    """Tests for yaml2json script."""

    def test_valid_yaml(self) -> None:
        """Test converting valid YAML to JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("key: value\nnumber: 42\n")
            yaml_file = f.name

        try:
            exit_code, stdout, stderr = run_yaml2json(yaml_file)
            assert exit_code == 0
            assert stderr == ""
            data = json.loads(stdout)
            assert data == {"key": "value", "number": 42}
        finally:
            Path(yaml_file).unlink(missing_ok=True)

    def test_empty_yaml(self) -> None:
        """Test handling empty YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")
            yaml_file = f.name

        try:
            exit_code, stdout, stderr = run_yaml2json(yaml_file)
            assert exit_code == 0
            assert stderr == ""
            data = json.loads(stdout)
            assert data == {}
        finally:
            Path(yaml_file).unlink(missing_ok=True)

    def test_yaml_with_datetime(self) -> None:
        """Test handling unquoted YAML timestamp (datetime type)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            # Unquoted dates in YAML are parsed as datetime objects
            f.write("created: 2025-01-14\nupdated: 2025-01-14T10:30:00\n")
            yaml_file = f.name

        try:
            exit_code, stdout, stderr = run_yaml2json(yaml_file)
            assert exit_code == 0
            assert stderr == ""
            data = json.loads(stdout)
            # datetime objects should be serialized as strings
            assert "created" in data
            assert "updated" in data
            assert "2025-01-14" in data["created"]
        finally:
            Path(yaml_file).unlink(missing_ok=True)

    def test_file_not_found(self) -> None:
        """Test handling non-existent file."""
        exit_code, _stdout, stderr = run_yaml2json("/nonexistent/file.yaml")
        assert exit_code == 1
        assert "File not found" in stderr

    @pytest.mark.skipif(os.geteuid() == 0, reason="Root can read any file regardless of permissions")
    def test_permission_error(self) -> None:
        """Test handling file permission errors."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("key: value\n")
            yaml_file = f.name

        try:
            # Remove read permissions
            os.chmod(yaml_file, 0)

            exit_code, _stdout, stderr = run_yaml2json(yaml_file)
            assert exit_code == 1
            assert "Cannot read file" in stderr or "Permission denied" in stderr
        finally:
            # Restore permissions for cleanup
            os.chmod(yaml_file, stat.S_IRUSR | stat.S_IWUSR)
            Path(yaml_file).unlink(missing_ok=True)

    def test_invalid_yaml(self) -> None:
        """Test handling invalid YAML syntax."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("key: [unclosed bracket\n")
            yaml_file = f.name

        try:
            exit_code, _stdout, stderr = run_yaml2json(yaml_file)
            assert exit_code == 1
            assert "Invalid YAML" in stderr
        finally:
            Path(yaml_file).unlink(missing_ok=True)

    def test_is_a_directory(self) -> None:
        """Test handling when path is a directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            exit_code, _stdout, stderr = run_yaml2json(tmpdir)
            assert exit_code == 1
            assert "Cannot read file" in stderr or "Is a directory" in stderr

    def test_no_arguments(self) -> None:
        """Test handling missing arguments."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "Usage:" in result.stderr
