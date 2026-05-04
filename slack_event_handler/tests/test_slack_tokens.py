"""Tests for slack_event_handler.utils.slack_tokens (no real Selenium)."""

from unittest.mock import MagicMock, patch

import pytest

from slack_event_handler.utils import slack_tokens as st


@pytest.fixture(autouse=True)
def reset_global_driver():
    st._global_driver = None
    yield
    st._global_driver = None


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:4444/wd/hub",
        "https://selenium.example.com/wd/hub/",
    ],
)
def test_validate_selenium_hub_url_ok(url):
    assert "/wd/hub" in st._validate_selenium_hub_url(url)


@pytest.mark.parametrize(
    "bad",
    ["", None, "ftp://x/wd/hub", "http://localhost:4444/no-hub"],
)
def test_validate_selenium_hub_url_bad(bad):
    with pytest.raises(ValueError):
        st._validate_selenium_hub_url(bad)


def test_validate_chrome_profile_path_ok():
    assert "/home/seluser/profile" in st._validate_chrome_profile_path(
        "/home/seluser/profile"
    )


@pytest.mark.parametrize(
    "bad",
    ["", None, "bad\x00path", "???"],
)
def test_validate_chrome_profile_path_bad(bad):
    with pytest.raises(ValueError):
        st._validate_chrome_profile_path(bad)


def test_extract_slack_tokens_success():
    driver = MagicMock()
    driver.execute_script.return_value = (
        '{"teams": {"T1": {"token": "xoxc", "name": "n", "user_id": "U1"}}}'
    )
    driver.get_cookies.return_value = [{"name": "d", "value": "xoxd-val"}]
    out = st.extract_slack_tokens(driver, "T1")
    assert out["xoxc"] == "xoxc"
    assert out["xoxd"] == "xoxd-val"


def test_extract_slack_tokens_no_local_config():
    driver = MagicMock()
    driver.execute_script.return_value = None
    assert st.extract_slack_tokens(driver, "T1") is None


def test_extract_slack_tokens_bad_json():
    driver = MagicMock()
    driver.execute_script.return_value = "{"
    assert st.extract_slack_tokens(driver, "T1") is None


def test_get_all_team_ids_returns_keys():
    driver = MagicMock()
    driver.execute_script.return_value = '{"teams": {"TA": {}, "TB": {}}}'
    assert set(st.get_all_team_ids(driver)) == {"TA", "TB"}


def test_get_all_team_ids_empty_on_error():
    driver = MagicMock()
    driver.execute_script.side_effect = RuntimeError("no")
    assert st.get_all_team_ids(driver) == []


@pytest.mark.django_db
def test_check_docker_selenium_connection_ok(settings):
    settings.SELENIUM_HUB_URL = "http://localhost:4444/wd/hub"

    class FakeResp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    with patch("urllib.request.urlopen", return_value=FakeResp()):
        assert st.check_docker_selenium_connection() is True


@pytest.mark.django_db
def test_open_chrome_browser_delegates(settings):
    settings.SELENIUM_HUB_URL = "http://localhost:4444/wd/hub"
    with patch.object(st, "check_docker_selenium_connection", return_value=True):
        assert st.open_chrome_browser() is True


@pytest.mark.django_db
def test_connect_to_chrome_uses_remote(settings):
    settings.SELENIUM_HUB_URL = "http://localhost:4444/wd/hub"
    settings.CHROME_PROFILE_PATH = "/home/seluser/chrome_profile"
    mock_driver = MagicMock()
    with patch.object(st.webdriver, "Remote", return_value=mock_driver):
        d = st.connect_to_chrome()
    assert d is mock_driver
    assert st._global_driver is mock_driver


@pytest.mark.django_db
def test_extract_slack_tokens_auto_stops_when_browser_unreachable(settings):
    settings.SELENIUM_HUB_URL = "http://localhost:4444/wd/hub"
    with patch.object(st, "open_chrome_browser", return_value=False):
        assert st.extract_slack_tokens_auto("T1") is None
