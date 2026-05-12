"""How core.errors.classify_failure treats exceptions from the YouTube stack.

googleapiclient.errors.HttpError is not specially classified today; it falls
through to UNKNOWN unless it subclasses a handled type.
"""

import pytest

from core.errors import CollectorFailureCategory, classify_failure
from cppa_youtube_script_tracker.fetcher import QuotaExceededError


class _FakeResp:
    def __init__(self, status: int, reason: str = "OK"):
        self.status = status
        self.reason = reason


def test_classify_failure_value_error_is_validation():
    assert classify_failure(ValueError("YOUTUBE_API_KEY is not set")) is (
        CollectorFailureCategory.VALIDATION
    )


def test_classify_failure_import_error_is_unknown():
    assert (
        classify_failure(ImportError("no module")) is CollectorFailureCategory.UNKNOWN
    )


def test_classify_failure_quota_exceeded_error_is_unknown():
    assert (
        classify_failure(QuotaExceededError("quota"))
        is CollectorFailureCategory.UNKNOWN
    )


def test_classify_failure_google_http_error_is_unknown_if_client_installed():
    try:
        from googleapiclient.errors import HttpError
    except ImportError:
        pytest.skip("google-api-python-client not installed")
    err = HttpError(resp=_FakeResp(403, "Forbidden"), content=b"{}")
    assert classify_failure(err) is CollectorFailureCategory.UNKNOWN
