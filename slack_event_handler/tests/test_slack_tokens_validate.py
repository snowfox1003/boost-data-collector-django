"""Tests for slack_tokens URL/path validation and token extraction helpers."""

import json
from unittest.mock import MagicMock

import pytest

from slack_event_handler.utils import slack_tokens as st
from slack_event_handler.utils.slack_tokens import (
    _validate_chrome_profile_path,
    _validate_selenium_hub_url,
)


def test_validate_selenium_hub_url_accepts_standard_hub():
    url = _validate_selenium_hub_url("http://localhost:4444/wd/hub/")
    assert url.endswith("/wd/hub")


def test_validate_selenium_hub_url_rejects_garbage():
    with pytest.raises(ValueError, match="SELENIUM_HUB_URL"):
        _validate_selenium_hub_url("not-a-hub")


def test_validate_selenium_hub_url_empty():
    with pytest.raises(ValueError):
        _validate_selenium_hub_url("")


def test_validate_chrome_profile_path_ok():
    assert _validate_chrome_profile_path("  /home/user/chrome-profile  ").startswith(
        "/"
    )


def test_validate_chrome_profile_path_null_byte():
    with pytest.raises(ValueError, match="null"):
        _validate_chrome_profile_path("/bad\x00path")


def test_extract_slack_tokens_success():
    driver = MagicMock()
    driver.execute_script.return_value = json.dumps(
        {"teams": {"T9": {"token": "xoxc-1", "name": "Team", "user_id": "U1"}}}
    )
    driver.get_cookies.return_value = [{"name": "d", "value": "xoxd-2"}]
    out = st.extract_slack_tokens(driver, "T9")
    assert out is not None
    assert out["xoxc"] == "xoxc-1"
    assert out["xoxd"] == "xoxd-2"


def test_extract_slack_tokens_missing_local_config():
    driver = MagicMock()
    driver.execute_script.return_value = None
    assert st.extract_slack_tokens(driver, "T1") is None


def test_get_all_team_ids_ok():
    driver = MagicMock()
    driver.execute_script.return_value = json.dumps({"teams": {"TA": {}, "TB": {}}})
    ids = st.get_all_team_ids(driver)
    assert set(ids) == {"TA", "TB"}
