"""Test run reporting for ISV Lab Service.

This module provides functions for creating and updating test runs
in the ISV Lab Service.
"""

import logging
import os
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def check_upload_credentials() -> tuple[bool, str | None, str | None]:
    """Check if ISV Lab Service credentials are available.

    Returns:
        Tuple of (can_upload, client_id, client_secret)
    """
    client_id = os.environ.get("ISV_CLIENT_ID")
    client_secret = os.environ.get("ISV_CLIENT_SECRET")

    if not client_id or not client_secret:
        return False, None, None

    return True, client_id, client_secret


def get_environment_config() -> tuple[str, str]:
    """Get ISV Lab Service endpoint and SSA issuer from environment.

    Returns:
        Tuple of (endpoint, ssa_issuer)
    """
    from isvreporter.config import get_default_endpoint, get_default_ssa_issuer

    endpoint = os.environ.get("ISV_LAB_SERVICE_ENDPOINT", get_default_endpoint())
    ssa_issuer = os.environ.get("ISV_SSA_ISSUER", get_default_ssa_issuer())
    return endpoint, ssa_issuer


def get_isv_test_version() -> str | None:
    """Get the isvctl package version for isv_test_version field.

    Returns:
        Package version string or None if not available
    """
    try:
        from isvctl import __version__

        return __version__
    except Exception:
        return None


def create_test_run(
    lab_id: int,
    platform: str,
    tags: list[str],
    start_time: str,
    executed_by: str = "isvctl",
    ci_reference: str = "local-run",
    isv_software_version: str | None = None,
) -> str | None:
    """Create a test run in ISV Lab Service.

    Args:
        lab_id: ISV Lab ID
        platform: Target platform (e.g., "kubernetes", "slurm")
        tags: List of tags for the test run
        start_time: ISO 8601 formatted start time
        executed_by: Tool that executed the test
        ci_reference: CI/CD reference identifier
        isv_software_version: ISV software stack version (opaque string from ISV)

    Returns:
        Test run ID if successful, None otherwise
    """
    try:
        from isvreporter.auth import get_jwt_token
        from isvreporter.client import create_test_run as client_create_test_run
    except ImportError:
        logger.warning("isvreporter not available, skipping result upload")
        return None

    can_upload, client_id, client_secret = check_upload_credentials()
    if not can_upload or not client_id or not client_secret:
        logger.info("ISV_CLIENT_ID / ISV_CLIENT_SECRET not set; skipping test-run creation")
        return None

    endpoint, ssa_issuer = get_environment_config()

    # Auto-detect ISV test version from package
    isv_test_version = get_isv_test_version()

    try:
        jwt_token = get_jwt_token(ssa_issuer, client_id, client_secret)
        result = client_create_test_run(
            endpoint=endpoint,
            lab_id=lab_id,
            jwt_token=jwt_token,
            test_target_type=platform.upper(),
            tags=tags,
            executed_by=executed_by,
            ci_reference=ci_reference,
            start_time=start_time,
            isv_software_version=isv_software_version,
            isv_test_version=isv_test_version,
        )
        return result.get("data", {}).get("testRunId")
    except SystemExit:
        # create_test_run calls sys.exit on failure, catch it
        logger.warning("Failed to create test run in ISV Lab Service")
        return None
    except Exception as e:
        logger.warning(f"Failed to create test run: {e}")
        return None


def update_test_run(
    lab_id: int,
    test_run_id: str,
    success: bool,
    start_time: str,
    log_file: Path | None = None,
    junit_xml: Path | None = None,
    log_content: str | None = None,
    isv_software_version: str | None = None,
) -> bool:
    """Update a test run in ISV Lab Service.

    Args:
        lab_id: ISV Lab ID
        test_run_id: Test run ID to update
        success: Whether tests succeeded
        start_time: ISO 8601 formatted start time (for duration calculation)
        log_file: Path to log file (optional)
        junit_xml: Path to JUnit XML file (optional)
        log_content: Direct log content string (optional, alternative to log_file)
        isv_software_version: ISV software stack version (opaque string from ISV)

    Returns:
        True if successful, False otherwise
    """
    try:
        from isvreporter.auth import get_jwt_token
        from isvreporter.client import report_test_results
        from isvreporter.client import update_test_run as client_update_test_run
    except ImportError:
        return False

    can_upload, client_id, client_secret = check_upload_credentials()
    if not can_upload or not client_id or not client_secret:
        logger.info("ISV_CLIENT_ID / ISV_CLIENT_SECRET not set; skipping test-run update")
        return False

    endpoint, ssa_issuer = get_environment_config()

    # Calculate duration
    try:
        start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        # Treat naive timestamps as UTC to avoid offset-naive/aware subtraction issues
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=UTC)
        duration_seconds = int((datetime.now(UTC) - start_dt).total_seconds())
    except Exception as e:
        logger.warning("Failed to compute test run duration from start_time=%r: %s", start_time, e)
        duration_seconds = None

    # Read log file if provided
    log_output = log_content
    if log_file and log_file.exists() and not log_output:
        try:
            log_output = log_file.read_text()
        except Exception as e:
            logger.warning(f"Failed to read log file: {e}")

    # Auto-detect ISV test version from package
    isv_test_version = get_isv_test_version()

    try:
        jwt_token = get_jwt_token(ssa_issuer, client_id, client_secret)

        # Upload JUnit XML test results first (if provided)
        if junit_xml and junit_xml.exists():
            try:
                logger.info("Uploading JUnit XML: %s", junit_xml)
                junit_content = junit_xml.read_text()
                report_test_results(
                    endpoint=endpoint,
                    lab_id=lab_id,
                    test_run_id=test_run_id,
                    jwt_token=jwt_token,
                    junit_xml=junit_content,
                )
            except SystemExit:
                # report_test_results uses sys.exit() on failure; log and continue
                logger.warning("Failed to upload JUnit XML to ISV Lab Service")
            except Exception as e:
                logger.warning("Failed to upload JUnit XML: %s", e)

        # Update test run with status and log, even if JUnit upload failed
        client_update_test_run(
            endpoint=endpoint,
            lab_id=lab_id,
            test_run_id=test_run_id,
            jwt_token=jwt_token,
            status="SUCCESS" if success else "FAILED",
            duration_seconds=duration_seconds,
            log_output=log_output,
            isv_software_version=isv_software_version,
            isv_test_version=isv_test_version,
        )
        return True
    except SystemExit:
        logger.warning("Failed to update test run in ISV Lab Service")
        return False
    except Exception as e:
        logger.warning(f"Failed to update test run: {e}")
        return False
