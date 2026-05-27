"""Tests for core.operations.slack_ops.fetcher."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
from django.test.utils import override_settings

from core.operations.slack_ops.fetcher import (
    SlackFetcher,
    download_file,
    fetch_huddle_transcript,
    get_file_info,
    get_slack_fetcher,
)
from slack_event_handler.utils import slack_internal_tokens_store as token_store


@pytest.fixture(autouse=True)
def _mock_default_slack_team():
    with patch(
        "core.operations.slack_ops.fetcher.get_default_team_key",
        return_value="T_TEST",
    ):
        yield


def test_slack_fetcher_uses_explicit_token():
    f = SlackFetcher(bot_token=" xoxb-test ")
    assert f.bot_token == "xoxb-test"


@patch("core.operations.slack_ops.fetcher.get_slack_client")
def test_slack_fetcher_default_client(mock_get_client):
    mock_get_client.return_value = MagicMock(token="xoxb-default")
    f = SlackFetcher()
    assert f._client == mock_get_client.return_value


def test_get_user_info_ok():
    client = MagicMock()
    client.users_info.return_value = {
        "ok": True,
        "user": {
            "name": "u1",
            "real_name": "Real",
            "profile": {"display_name": "Disp"},
        },
    }
    f = SlackFetcher(bot_token="t")
    f._client = client
    out = f.get_user_info("U1")
    assert out["display_name"] == "Disp"


def test_get_user_info_not_ok_fallback():
    client = MagicMock()
    client.users_info.return_value = {"ok": False}
    f = SlackFetcher(bot_token="t")
    f._client = client
    out = f.get_user_info("U9")
    assert out["name"] == "U9"


def test_get_user_info_exception_fallback():
    client = MagicMock()
    client.users_info.side_effect = RuntimeError("boom")
    f = SlackFetcher(bot_token="t")
    f._client = client
    out = f.get_user_info("Ux")
    assert out["real_name"] == "Ux"


def test_get_channel_info_ok_and_fallback():
    client = MagicMock()
    client.conversations_info.return_value = {
        "ok": True,
        "channel": {"name": "general"},
    }
    f = SlackFetcher(bot_token="t")
    f._client = client
    assert f.get_channel_info("C1") == "general"

    client.conversations_info.return_value = {"ok": False}
    assert f.get_channel_info("C2") == "C2"

    client.conversations_info.side_effect = RuntimeError("x")
    assert f.get_channel_info("C3") == "C3"


def test_get_file_info_ok():
    client = MagicMock()
    client.files_info.return_value = {"ok": True, "file": {"id": "F1"}}
    f = SlackFetcher(bot_token="t")
    f._client = client
    assert f.get_file_info("F1")["ok"] is True


def test_get_file_info_retries_then_ok():
    client = MagicMock()
    client.files_info.side_effect = [
        requests.exceptions.ConnectionError("fail"),
        {"ok": True, "file": {}},
    ]
    f = SlackFetcher(bot_token="t")
    f._client = client
    with patch("core.operations.slack_ops.fetcher.time.sleep"):
        out = f.get_file_info("F1", max_retries=2, retry_delay=0)
    assert out["ok"] is True


def test_get_file_info_generic_exception_returns_none():
    client = MagicMock()
    client.files_info.side_effect = ValueError("weird")
    f = SlackFetcher(bot_token="t")
    f._client = client
    assert f.get_file_info("F1") is None


def _mock_response_ok(body_chunks, headers=None):
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = headers or {}
    resp.iter_content.return_value = body_chunks
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


@patch("core.operations.slack_ops.fetcher.requests.get")
def test_download_file_success(mock_get, tmp_path):
    mock_get.return_value = _mock_response_ok(
        [b"hi"], headers={"Content-Disposition": 'attachment; filename="f.txt"'}
    )
    f = SlackFetcher(bot_token="tok")
    path = f.download_file("https://files.slack.com/x", save_path=str(tmp_path))
    assert path is not None
    assert Path(path).exists()


@patch("core.operations.slack_ops.fetcher.requests.get")
def test_download_file_utf8_filename_star(mock_get, tmp_path):
    mock_get.return_value = _mock_response_ok(
        [b"x"],
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''hello%20world.txt"
        },
    )
    f = SlackFetcher(bot_token="tok")
    path = f.download_file("https://example.com/f", save_path=str(tmp_path))
    assert Path(path).name == "hello_world.txt"


@patch("core.operations.slack_ops.fetcher.requests.get")
def test_download_file_plain_filename_in_disposition(mock_get, tmp_path):
    mock_get.return_value = _mock_response_ok(
        [b"z"],
        headers={"Content-Disposition": 'attachment; filename="plain.txt"'},
    )
    f = SlackFetcher(bot_token="tok")
    path = f.download_file("https://example.com/f", save_path=str(tmp_path))
    assert path.endswith("plain.txt")


@patch("core.operations.slack_ops.fetcher.requests.get")
def test_download_file_http_error_no_retry_when_single_attempt(mock_get, tmp_path):
    bad = MagicMock(status_code=500)
    bad.__enter__ = MagicMock(return_value=bad)
    bad.__exit__ = MagicMock(return_value=False)
    mock_get.return_value = bad
    f = SlackFetcher(bot_token="tok")
    assert f.download_file("https://x", save_path=str(tmp_path), max_retries=1) is None


@patch("core.operations.slack_ops.fetcher.requests.get")
def test_download_file_bad_status_retries(mock_get, tmp_path):
    bad = MagicMock(status_code=500)
    bad.__enter__ = MagicMock(return_value=bad)
    bad.__exit__ = MagicMock(return_value=False)
    mock_get.side_effect = [
        bad,
        _mock_response_ok([b"a"], headers={}),
    ]
    f = SlackFetcher(bot_token="tok")
    with patch("core.operations.slack_ops.fetcher.time.sleep"):
        path = f.download_file("https://x", save_path=str(tmp_path), max_retries=2)
    assert path is not None


def test_get_file_and_download_missing_url(tmp_path):
    client = MagicMock()
    client.files_info.return_value = {"ok": True, "file": {"name": "n"}}
    f = SlackFetcher(bot_token="t")
    f._client = client
    finfo, path = f.get_file_and_download("F9", save_path=str(tmp_path))
    assert finfo["ok"]
    assert path is None


@patch("core.operations.slack_ops.fetcher.SlackFetcher")
def test_standalone_get_file_info_and_download_file(MockFetcher):
    inst = MagicMock()
    inst.get_file_info.return_value = {"ok": True}
    inst.download_file.return_value = "/tmp/x"
    MockFetcher.return_value = inst
    assert get_file_info("F1", bot_token="t")["ok"]
    assert download_file("http://u", bot_token="t") == "/tmp/x"


def test_get_slack_fetcher_factory():
    assert isinstance(get_slack_fetcher("x"), SlackFetcher)


@override_settings(WORKSPACE_DIR="/tmp/ws")
def test_save_slack_internal_tokens_json(tmp_path, settings):
    settings.WORKSPACE_DIR = str(tmp_path)
    path = token_store.save_slack_internal_tokens("T1", "xc", "xd")
    assert path.is_file()
    loaded = token_store.load_slack_internal_tokens("T1")
    assert loaded["xoxc"] == "xc"
    assert loaded["xoxd"] == "xd"


@override_settings(ALLOW_INTERNAL_SLACK_TOKENS=True, WORKSPACE_DIR="/tmp/ws")
@patch(
    "slack_event_handler.utils.slack_internal_tokens_store.get_or_load_slack_internal_token_pair",
    return_value=("xc", "xd"),
)
@patch("core.operations.slack_ops.fetcher.requests.post")
@patch("core.operations.slack_ops.fetcher.get_default_team_key", return_value="T1")
def test_fetch_huddle_transcript_ok(_mock_team, mock_post, _mock_load):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"ok": True, "file": {}}
    mock_post.return_value = mock_resp
    assert fetch_huddle_transcript("F1")["ok"] is True


@override_settings(ALLOW_INTERNAL_SLACK_TOKENS=True)
@patch(
    "slack_event_handler.utils.slack_internal_tokens_store.get_or_load_slack_internal_token_pair",
    return_value=("xc", "xd"),
)
@patch("core.operations.slack_ops.fetcher.requests.post")
@patch("core.operations.slack_ops.fetcher.get_default_team_key", return_value="T1")
def test_fetch_huddle_transcript_connection_error(_mock_team, mock_post, _pair):
    mock_post.side_effect = requests.exceptions.ConnectionError("down")
    with patch("core.operations.slack_ops.fetcher.time.sleep"):
        assert fetch_huddle_transcript("F1") is None


def test_get_file_info_returns_slack_error_payload():
    client = MagicMock()
    client.files_info.return_value = {"ok": False, "error": "file_not_found"}
    f = SlackFetcher(bot_token="t")
    f._client = client
    out = f.get_file_info("Fz")
    assert out["ok"] is False


def test_get_file_info_network_retries_then_exhausted():
    client = MagicMock()
    client.files_info.side_effect = requests.exceptions.ConnectionError("x")
    f = SlackFetcher(bot_token="t")
    f._client = client
    with patch("core.operations.slack_ops.fetcher.time.sleep"):
        assert f.get_file_info("F1", max_retries=2, retry_delay=0) is None


def test_get_file_info_zero_retries_returns_none():
    client = MagicMock()
    f = SlackFetcher(bot_token="t")
    f._client = client
    assert f.get_file_info("F0", max_retries=0) is None


@patch("core.operations.slack_ops.fetcher.requests.get")
def test_download_file_uses_cwd_when_save_path_none(mock_get, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mock_get.return_value = _mock_response_ok([b"x"], headers={})
    f = SlackFetcher(bot_token="tok")
    path = f.download_file(
        "https://example.com/a.bin", save_path=None, filename="f.bin"
    )
    assert path is not None
    assert Path(path).exists()


@patch("core.operations.slack_ops.fetcher.requests.get")
def test_download_file_network_error_exhausted(mock_get, tmp_path):
    mock_get.side_effect = requests.exceptions.ConnectionError("nope")
    f = SlackFetcher(bot_token="tok")
    with patch("core.operations.slack_ops.fetcher.time.sleep"):
        assert (
            f.download_file("https://x", save_path=str(tmp_path), max_retries=2) is None
        )


@patch("core.operations.slack_ops.fetcher.requests.get")
def test_download_file_generic_exception(mock_get, tmp_path):
    mock_get.side_effect = ValueError("bad")
    f = SlackFetcher(bot_token="tok")
    assert f.download_file("https://x", save_path=str(tmp_path)) is None


@patch("core.operations.slack_ops.fetcher.requests.get")
def test_download_file_zero_max_retries_returns_none_without_request(
    mock_get, tmp_path
):
    f = SlackFetcher(bot_token="tok")
    assert f.download_file("https://x", save_path=str(tmp_path), max_retries=0) is None
    mock_get.assert_not_called()


def test_get_file_and_download_when_get_file_info_fails():
    f = SlackFetcher(bot_token="t")
    with patch.object(f, "get_file_info", return_value=None):
        finfo, path = f.get_file_and_download("Fx")
    assert finfo is None and path is None


def test_get_file_and_download_when_not_ok():
    f = SlackFetcher(bot_token="t")
    with patch.object(f, "get_file_info", return_value={"ok": False}):
        finfo, path = f.get_file_and_download("Fx")
    assert finfo is None and path is None


def test_get_file_and_download_with_private_url(tmp_path):
    f = SlackFetcher(bot_token="tok")
    with patch.object(f, "get_file_info") as gi, patch.object(f, "download_file") as dl:
        gi.return_value = {
            "ok": True,
            "file": {
                "url_private_download": "https://files.slack.com/dl",
                "name": "n.txt",
            },
        }
        dl.return_value = str(tmp_path / "n.txt")
        finfo, path = f.get_file_and_download("F1", save_path=str(tmp_path))
        assert finfo["ok"]
        assert path.endswith("n.txt")


def test_save_slack_internal_tokens_write_error(tmp_path, settings):
    settings.WORKSPACE_DIR = str(tmp_path)
    with patch.object(token_store, "_write_document", side_effect=OSError("perm")):
        with pytest.raises(OSError):
            token_store.save_slack_internal_tokens("T1", "a", "b")


@override_settings(ALLOW_INTERNAL_SLACK_TOKENS=True)
@patch(
    "slack_event_handler.utils.slack_internal_tokens_store.get_or_load_slack_internal_token_pair",
    return_value=("xc", "xd"),
)
@patch("core.operations.slack_ops.fetcher.requests.post")
@patch("core.operations.slack_ops.fetcher.get_default_team_key", return_value="T1")
def test_fetch_huddle_loads_tokens_from_json(
    _mock_team,
    mock_post,
    _mock_load,
):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"ok": True, "file": {}}
    mock_post.return_value = mock_resp
    assert fetch_huddle_transcript("F9")["ok"] is True


@override_settings(ALLOW_INTERNAL_SLACK_TOKENS=True)
@patch(
    "slack_event_handler.utils.slack_internal_tokens_store.get_or_load_slack_internal_token_pair",
    return_value=None,
)
@patch("core.operations.slack_ops.fetcher.get_default_team_key", return_value=None)
def test_fetch_huddle_missing_tokens_and_no_team(_mock_team, _mock_load):
    assert fetch_huddle_transcript("F1") is None


@override_settings(ALLOW_INTERNAL_SLACK_TOKENS=True)
@patch(
    "slack_event_handler.utils.slack_internal_tokens_store.get_or_load_slack_internal_token_pair",
    return_value=None,
)
@patch("core.operations.slack_ops.fetcher.get_default_team_key", return_value="T1")
def test_fetch_huddle_extract_returns_invalid(_mock_team, _mock_load):
    assert fetch_huddle_transcript("F1") is None


@override_settings(ALLOW_INTERNAL_SLACK_TOKENS=True)
@patch(
    "slack_event_handler.utils.slack_internal_tokens_store._extract_validate_and_return",
    return_value=("nxc", "nxd"),
)
@patch(
    "slack_event_handler.utils.slack_internal_tokens_store.get_or_load_slack_internal_token_pair",
    return_value=("xc", "xd"),
)
@patch("core.operations.slack_ops.fetcher.requests.post")
@patch("core.operations.slack_ops.fetcher.get_default_team_key", return_value="T1")
def test_fetch_huddle_reextracts_from_profile_on_auth_error(
    _mock_team,
    mock_post,
    _mock_load,
    _mock_reextract,
):
    ok_resp = MagicMock()
    ok_resp.raise_for_status = MagicMock()
    ok_resp.json.return_value = {"ok": True, "file": {}}
    bad_resp = MagicMock()
    bad_resp.raise_for_status = MagicMock()
    bad_resp.json.return_value = {"ok": False, "error": "token_revoked"}
    mock_post.side_effect = [bad_resp, ok_resp]
    assert fetch_huddle_transcript("Fx")["ok"] is True
    _mock_reextract.assert_called_once_with("T1")


@override_settings(ALLOW_INTERNAL_SLACK_TOKENS=True)
@patch(
    "slack_event_handler.utils.slack_internal_tokens_store._extract_validate_and_return",
    return_value=("nxc", "nxd"),
)
@patch(
    "slack_event_handler.utils.slack_internal_tokens_store.get_or_load_slack_internal_token_pair",
    return_value=("xc", "xd"),
)
@patch("core.operations.slack_ops.fetcher.requests.post")
@patch("core.operations.slack_ops.fetcher.get_default_team_key", return_value="T1")
def test_fetch_huddle_reextracts_after_connection_error_then_auth_error(
    _mock_team,
    mock_post,
    _mock_load,
    _mock_reextract,
):
    """Auth on a later attempt must still trigger one re-extract (not gated on attempt == 0)."""
    ok_resp = MagicMock()
    ok_resp.raise_for_status = MagicMock()
    ok_resp.json.return_value = {"ok": True, "file": {}}
    bad_resp = MagicMock()
    bad_resp.raise_for_status = MagicMock()
    bad_resp.json.return_value = {"ok": False, "error": "token_revoked"}
    mock_post.side_effect = [
        requests.exceptions.ConnectionError("down"),
        bad_resp,
        ok_resp,
    ]
    with patch("core.operations.slack_ops.fetcher.time.sleep"):
        assert fetch_huddle_transcript("Fx")["ok"] is True
    _mock_reextract.assert_called_once_with("T1")


@override_settings(ALLOW_INTERNAL_SLACK_TOKENS=True)
@patch(
    "slack_event_handler.utils.slack_internal_tokens_store._extract_validate_and_return",
    return_value=None,
)
@patch(
    "slack_event_handler.utils.slack_internal_tokens_store.get_or_load_slack_internal_token_pair",
    return_value=("xc", "xd"),
)
@patch("core.operations.slack_ops.fetcher.requests.post")
@patch("core.operations.slack_ops.fetcher.get_default_team_key", return_value="T1")
def test_fetch_huddle_auth_error_when_reextract_fails(
    _mock_team, mock_post, _mock_load, _mock_reextract, caplog
):
    import logging

    bad_resp = MagicMock()
    bad_resp.raise_for_status = MagicMock()
    bad_resp.json.return_value = {"ok": False, "error": "token_revoked"}
    mock_post.return_value = bad_resp
    with caplog.at_level(logging.ERROR):
        assert fetch_huddle_transcript("Fx") is None
    _mock_reextract.assert_called_once_with("T1")
    assert "slack-tokens-refresh" in caplog.text


@override_settings(ALLOW_INTERNAL_SLACK_TOKENS=True)
@patch(
    "slack_event_handler.utils.slack_internal_tokens_store.get_or_load_slack_internal_token_pair",
    return_value=("xc", "xd"),
)
@patch("core.operations.slack_ops.fetcher.requests.post")
@patch("core.operations.slack_ops.fetcher.get_default_team_key", return_value="T1")
def test_fetch_huddle_returns_error_payload_when_not_ok(
    _mock_team, mock_post, _mock_pair
):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"ok": False, "error": "invalid"}
    mock_post.return_value = mock_resp
    out = fetch_huddle_transcript("Fz")
    assert out["ok"] is False


@override_settings(ALLOW_INTERNAL_SLACK_TOKENS=True)
@patch(
    "slack_event_handler.utils.slack_internal_tokens_store.get_or_load_slack_internal_token_pair",
    return_value=("xc", "xd"),
)
@patch("core.operations.slack_ops.fetcher.requests.post")
@patch("core.operations.slack_ops.fetcher.get_default_team_key", return_value="T1")
def test_fetch_huddle_unexpected_exception_returns_none(
    _mock_team, mock_post, _mock_pair
):
    mock_post.side_effect = ValueError("weird")
    assert fetch_huddle_transcript("Fe") is None
