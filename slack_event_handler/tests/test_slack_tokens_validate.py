"""Validation helpers for slack_tokens."""

import pytest

from slack_event_handler.utils.slack_tokens import (
    _validate_chrome_profile_path,
)


def test_validate_chrome_profile_path_accepts_standard_path():
    path = _validate_chrome_profile_path("  /home/user/chrome-profile  ")
    assert path.startswith("/")


def test_validate_chrome_profile_path_rejects_null_byte():
    with pytest.raises(ValueError, match="null bytes"):
        _validate_chrome_profile_path("/bad\x00path")


def test_validate_chrome_profile_path_empty():
    with pytest.raises(ValueError):
        _validate_chrome_profile_path("")
