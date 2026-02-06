"""Shared AWS error classification utilities.

Provides consistent error type classification for all AWS scripts.
"""

import functools
import json
from collections.abc import Callable

from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    NoCredentialsError,
    ProfileNotFound,
    TokenRetrievalError,
)


def classify_aws_error(e: Exception) -> tuple[str, str]:
    """Classify AWS error into error_type and message.

    Returns:
        Tuple of (error_type, error_message) where error_type is one of:
        - credentials_missing: No AWS credentials configured
        - credentials_expired: Token/session expired
        - credentials_invalid: Invalid signature or keys
        - profile_not_found: AWS profile doesn't exist
        - access_denied: Valid creds but insufficient permissions
        - aws_error: Other AWS API errors
        - unknown_error: Non-AWS exceptions
    """
    if isinstance(e, NoCredentialsError):
        return "credentials_missing", "AWS credentials not found"
    if isinstance(e, ProfileNotFound):
        return "profile_not_found", f"AWS profile not found: {e}"
    if isinstance(e, TokenRetrievalError):
        return "credentials_expired", "AWS credentials expired - please refresh"
    if isinstance(e, ClientError):
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("ExpiredToken", "ExpiredTokenException"):
            return "credentials_expired", "AWS credentials expired - please refresh"
        if code in ("InvalidSignatureException", "SignatureDoesNotMatch"):
            return "credentials_invalid", "AWS credentials invalid or expired"
        if code in ("InvalidClientTokenId", "AuthFailure"):
            return "credentials_invalid", "AWS credentials are invalid"
        if code == "AccessDenied":
            return "access_denied", f"Access denied: {e}"
        return "aws_error", str(e)
    if isinstance(e, BotoCoreError):
        return "aws_error", str(e)
    return "unknown_error", str(e)


def handle_aws_errors[**P](func: Callable[P, int]) -> Callable[P, int]:
    """Decorator that catches AWS errors and outputs structured JSON.

    Scripts still print their own JSON and return 0/1.
    This decorator only catches uncaught exceptions (like boto3.client() failing).

    Usage:
        @handle_aws_errors
        def main() -> int:
            # ... do work, print JSON ...
            return 0 if success else 1

        if __name__ == "__main__":
            sys.exit(main())
    """

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> int:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_type, error_msg = classify_aws_error(e)
            print(json.dumps({"success": False, "error_type": error_type, "error": error_msg}, indent=2))
            return 1

    return wrapper
