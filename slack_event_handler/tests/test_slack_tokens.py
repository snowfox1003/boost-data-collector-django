"""Tests for slack_event_handler.utils.slack_tokens (no real Selenium)."""

from unittest.mock import MagicMock, PropertyMock, patch

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


def test_extract_slack_tokens_team_missing():
    driver = MagicMock()
    driver.execute_script.return_value = (
        '{"teams": {"T2": {"token": "x", "name": "n"}}}'
    )
    assert st.extract_slack_tokens(driver, "T1") is None


def test_extract_slack_tokens_missing_xoxc():
    driver = MagicMock()
    driver.execute_script.return_value = '{"teams": {"T1": {"name": "n"}}}'
    assert st.extract_slack_tokens(driver, "T1") is None


def test_extract_slack_tokens_missing_xoxd_cookie():
    driver = MagicMock()
    driver.execute_script.return_value = (
        '{"teams": {"T1": {"token": "xoxc", "name": "n", "user_id": "U"}}}'
    )
    driver.get_cookies.return_value = [{"name": "other", "value": "v"}]
    assert st.extract_slack_tokens(driver, "T1") is None


def test_extract_slack_tokens_generic_exception():
    driver = MagicMock()
    driver.execute_script.side_effect = OSError("boom")
    assert st.extract_slack_tokens(driver, "T1") is None


def test_get_all_team_ids_empty_local_config():
    driver = MagicMock()
    driver.execute_script.return_value = None
    assert st.get_all_team_ids(driver) == []


@pytest.mark.django_db
def test_check_docker_selenium_non_200(settings):
    settings.SELENIUM_HUB_URL = "http://localhost:4444/wd/hub"

    class FakeResp:
        status = 500

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    with patch("urllib.request.urlopen", return_value=FakeResp()):
        assert st.check_docker_selenium_connection() is False


@pytest.mark.django_db
def test_check_docker_selenium_socket_timeout(settings):
    settings.SELENIUM_HUB_URL = "http://localhost:4444/wd/hub"
    import socket

    with patch("urllib.request.urlopen", side_effect=socket.timeout()):
        assert st.check_docker_selenium_connection() is False


@pytest.mark.django_db
def test_check_docker_selenium_url_error(settings):
    settings.SELENIUM_HUB_URL = "http://localhost:4444/wd/hub"
    import urllib.error

    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError("refused"),
    ):
        assert st.check_docker_selenium_connection() is False


@pytest.mark.django_db
def test_check_docker_selenium_outer_exception(settings):
    with patch.object(
        st, "_validate_selenium_hub_url", side_effect=RuntimeError("bad")
    ):
        assert st.check_docker_selenium_connection() is False


@pytest.mark.django_db
def test_connect_to_chrome_reuses_live_driver(settings):
    settings.SELENIUM_HUB_URL = "http://localhost:4444/wd/hub"
    settings.CHROME_PROFILE_PATH = "/home/seluser/chrome_profile"
    existing = MagicMock()
    existing.current_url = "http://example.com"
    st._global_driver = existing
    assert st.connect_to_chrome() is existing


@pytest.mark.django_db
def test_connect_to_chrome_recreates_when_stale(settings):
    settings.SELENIUM_HUB_URL = "http://localhost:4444/wd/hub"
    settings.CHROME_PROFILE_PATH = "/home/seluser/chrome_profile"
    stale = MagicMock()
    type(stale).current_url = PropertyMock(side_effect=OSError("gone"))
    fresh = MagicMock()
    st._global_driver = stale
    with patch.object(st.webdriver, "Remote", return_value=fresh):
        d = st.connect_to_chrome()
    assert d is fresh
    assert st._global_driver is fresh


@pytest.mark.django_db
def test_connect_to_chrome_remote_failure_returns_none(settings):
    settings.SELENIUM_HUB_URL = "http://localhost:4444/wd/hub"
    settings.CHROME_PROFILE_PATH = "/home/seluser/chrome_profile"
    st._global_driver = None
    with patch.object(st.webdriver, "Remote", side_effect=OSError("no hub")):
        assert st.connect_to_chrome() is None


@pytest.mark.django_db
def test_extract_slack_tokens_auto_happy_path(settings):
    settings.SELENIUM_HUB_URL = "http://localhost:4444/wd/hub"
    settings.CHROME_PROFILE_PATH = "/home/seluser/chrome_profile"

    driver = MagicMock()
    driver.current_url = "https://app.slack.com/client/T1/channel"

    with patch.object(st, "open_chrome_browser", return_value=True):
        with patch.object(st, "connect_to_chrome", return_value=driver):
            with patch("slack_event_handler.utils.slack_tokens.time.sleep"):
                with patch.object(
                    st,
                    "extract_slack_tokens",
                    return_value={"xoxc": "a", "xoxd": "b"},
                ):
                    out = st.extract_slack_tokens_auto("T1")
    assert out["xoxc"] == "a"


@pytest.mark.django_db
def test_extract_slack_tokens_auto_navigate_when_not_on_slack(settings):
    settings.SELENIUM_HUB_URL = "http://localhost:4444/wd/hub"
    settings.CHROME_PROFILE_PATH = "/home/seluser/chrome_profile"
    driver = MagicMock()
    urls = iter(["about:blank", "https://app.slack.com/client/T1/x"])
    type(driver).current_url = PropertyMock(side_effect=lambda: next(urls))

    with patch.object(st, "open_chrome_browser", return_value=True):
        with patch.object(st, "connect_to_chrome", return_value=driver):
            with patch("slack_event_handler.utils.slack_tokens.time.sleep"):
                with patch.object(
                    st,
                    "extract_slack_tokens",
                    return_value={"xoxc": "a", "xoxd": "b"},
                ):
                    assert st.extract_slack_tokens_auto("T1") is not None
    driver.get.assert_called()


@pytest.mark.django_db
def test_extract_slack_tokens_auto_current_url_raises_then_get(settings):
    settings.SELENIUM_HUB_URL = "http://localhost:4444/wd/hub"
    settings.CHROME_PROFILE_PATH = "/home/seluser/chrome_profile"
    driver = MagicMock()
    urls = iter([OSError("no url yet"), "https://app.slack.com/x"])
    type(driver).current_url = PropertyMock(side_effect=lambda: next(urls))

    with patch.object(st, "open_chrome_browser", return_value=True):
        with patch.object(st, "connect_to_chrome", return_value=driver):
            with patch("slack_event_handler.utils.slack_tokens.time.sleep"):
                with patch.object(
                    st,
                    "extract_slack_tokens",
                    return_value={"xoxc": "a", "xoxd": "b"},
                ):
                    st.extract_slack_tokens_auto("T1")
    driver.get.assert_called()


@pytest.mark.django_db
def test_extract_slack_tokens_auto_not_slack_page_returns_none(settings):
    settings.SELENIUM_HUB_URL = "http://localhost:4444/wd/hub"
    settings.CHROME_PROFILE_PATH = "/home/seluser/chrome_profile"
    driver = MagicMock()
    driver.current_url = "https://evil.example/page"

    with patch.object(st, "open_chrome_browser", return_value=True):
        with patch.object(st, "connect_to_chrome", return_value=driver):
            with patch("slack_event_handler.utils.slack_tokens.time.sleep"):
                assert st.extract_slack_tokens_auto("T1") is None


@pytest.mark.django_db
def test_extract_slack_tokens_auto_extraction_failure_returns_none(settings):
    settings.SELENIUM_HUB_URL = "http://localhost:4444/wd/hub"
    settings.CHROME_PROFILE_PATH = "/home/seluser/chrome_profile"
    driver = MagicMock()
    driver.current_url = "https://app.slack.com/client/T1/x"

    with patch.object(st, "open_chrome_browser", return_value=True):
        with patch.object(st, "connect_to_chrome", return_value=driver):
            with patch("slack_event_handler.utils.slack_tokens.time.sleep"):
                with patch.object(st, "extract_slack_tokens", return_value=None):
                    assert st.extract_slack_tokens_auto("T1") is None


@pytest.mark.django_db
def test_extract_slack_tokens_auto_outer_exception_returns_none(settings):
    settings.SELENIUM_HUB_URL = "http://localhost:4444/wd/hub"
    settings.CHROME_PROFILE_PATH = "/home/seluser/chrome_profile"
    driver = MagicMock()
    driver.current_url = "https://app.slack.com/client/T1/x"

    with patch.object(st, "open_chrome_browser", return_value=True):
        with patch.object(st, "connect_to_chrome", return_value=driver):
            with patch(
                "slack_event_handler.utils.slack_tokens.time.sleep",
                side_effect=RuntimeError("boom"),
            ):
                assert st.extract_slack_tokens_auto("T1") is None
