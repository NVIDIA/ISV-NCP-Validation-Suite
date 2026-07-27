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

"""Tests for the ISV Lab Service API client."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from isvreporter.client import calculate_duration, create_test_run, load_test_run_id


class TestCalculateDuration:
    """Tests for calculate_duration function."""

    def test_calculate_duration(self) -> None:
        """Test duration calculation from ISO 8601 timestamp."""
        # This is a basic smoke test - more comprehensive tests would use mocking
        # for the actual API calls
        start_time = "2024-01-01T12:00:00Z"
        duration = calculate_duration(start_time)

        # Duration should be positive (we're calculating from past to now)
        assert duration > 0
        assert isinstance(duration, int)

    def test_calculate_duration_with_timezone(self) -> None:
        """Test duration calculation with explicit timezone."""
        start_time = "2024-01-01T12:00:00+00:00"
        duration = calculate_duration(start_time)

        assert duration > 0
        assert isinstance(duration, int)


class TestLoadTestRunId:
    """Tests for load_test_run_id function."""

    def test_load_existing_test_run_id(self, tmp_path: Path) -> None:
        """Test loading test run ID from existing file."""
        # Create test file
        output_dir = tmp_path / "_output"
        output_dir.mkdir()
        test_run_file = output_dir / "testrun_id.txt"
        test_run_file.write_text("test-run-12345")

        with patch("isvreporter.client.TEST_RUN_ID_FILE", test_run_file):
            result = load_test_run_id()
            assert result == "test-run-12345"

    def test_load_test_run_id_strips_whitespace(self, tmp_path: Path) -> None:
        """Test that whitespace is stripped from test run ID."""
        output_dir = tmp_path / "_output"
        output_dir.mkdir()
        test_run_file = output_dir / "testrun_id.txt"
        test_run_file.write_text("  test-run-67890  \n")

        with patch("isvreporter.client.TEST_RUN_ID_FILE", test_run_file):
            result = load_test_run_id()
            assert result == "test-run-67890"

    def test_load_test_run_id_file_not_found(self, tmp_path: Path) -> None:
        """Test that None is returned when file doesn't exist."""
        nonexistent_file = tmp_path / "_output" / "testrun_id.txt"

        with patch("isvreporter.client.TEST_RUN_ID_FILE", nonexistent_file):
            result = load_test_run_id()
            assert result is None

    def test_load_empty_test_run_id(self, tmp_path: Path) -> None:
        """Test loading empty test run ID file."""
        output_dir = tmp_path / "_output"
        output_dir.mkdir()
        test_run_file = output_dir / "testrun_id.txt"
        test_run_file.write_text("")

        with patch("isvreporter.client.TEST_RUN_ID_FILE", test_run_file):
            result = load_test_run_id()
            assert result == ""


class TestCreateTestRunPayload:
    """The create payload has to carry both axes of what the run exercised."""

    @staticmethod
    def _posted_payload(mock_urlopen: MagicMock) -> dict[str, Any]:
        """Return the JSON body of the request the client posted."""
        request = mock_urlopen.call_args[0][0]
        return json.loads(request.data.decode())

    @staticmethod
    def _response() -> MagicMock:
        """Return a context-manager response yielding a created test run id."""
        response = MagicMock()
        response.read.return_value = json.dumps({"data": {"testRunId": 42}}).encode()
        response.__enter__ = lambda self: self
        response.__exit__ = lambda *args: False
        return response

    @patch("isvreporter.client.urlopen")
    def test_sends_suite_and_capability(self, mock_urlopen: MagicMock, tmp_path: Path) -> None:
        """Both axes of the run reach the service in the create payload."""
        mock_urlopen.return_value = self._response()

        with (
            patch("isvreporter.client.OUTPUT_DIR", tmp_path),
            patch("isvreporter.client.TEST_RUN_ID_FILE", tmp_path / "testrun_id.txt"),
        ):
            create_test_run(
                endpoint="https://api.example.com",
                lab_id=1,
                jwt_token="jwt",
                test_target_type="VM",
                tags=[],
                executed_by="isvctl",
                ci_reference="local-run",
                start_time="2026-07-24T12:00:00Z",
                suite="network",
                capability="vm",
            )

        payload = self._posted_payload(mock_urlopen)
        assert payload["suite"] == "network"
        assert payload["capability"] == "vm"

    @patch("isvreporter.client.urlopen")
    def test_core_only_run_omits_capability(self, mock_urlopen: MagicMock, tmp_path: Path) -> None:
        """A core-only run sends no capability - the absence is the signal.

        Sending a sentinel instead would make it indistinguishable from a real
        capability in every downstream filter and column.
        """
        mock_urlopen.return_value = self._response()

        with (
            patch("isvreporter.client.OUTPUT_DIR", tmp_path),
            patch("isvreporter.client.TEST_RUN_ID_FILE", tmp_path / "testrun_id.txt"),
        ):
            create_test_run(
                endpoint="https://api.example.com",
                lab_id=1,
                jwt_token="jwt",
                test_target_type="NETWORK",
                tags=[],
                executed_by="isvctl",
                ci_reference="local-run",
                start_time="2026-07-24T12:00:00Z",
                suite="network",
                capability=None,
            )

        payload = self._posted_payload(mock_urlopen)
        assert payload["suite"] == "network"
        assert "capability" not in payload
