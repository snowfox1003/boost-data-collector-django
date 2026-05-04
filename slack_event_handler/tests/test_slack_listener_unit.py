"""Unit tests for slack_event_handler.utils.slack_listener (Bolt mocked)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.django_db
def test_save_event_to_file_writes_json(tmp_path, fake_slack_bolt):
    from slack_event_handler.utils import slack_listener as sl

    with patch.object(sl, "_data_dir", return_value=str(tmp_path)):
        p = sl.save_event_to_file("myevt", {"event": {"ts": "3.141"}})
    assert p is not None
    assert Path(p).exists()


@pytest.mark.django_db
def test_save_event_to_file_returns_none_on_error(tmp_path, fake_slack_bolt):
    from slack_event_handler.utils import slack_listener as sl

    with patch.object(sl, "_data_dir", return_value=str(tmp_path)):
        with patch.object(sl.json, "dump", side_effect=OSError("fail")):
            assert sl.save_event_to_file("x", {"event": {"ts": "1"}}) is None


@pytest.mark.django_db
def test_slack_listener_helpers(settings, fake_slack_bolt):
    from slack_event_handler.utils.slack_listener import SlackListener

    settings.SLACK_TEAM_SCOPE = {}
    settings.SLACK_PR_BOT_CHANNEL_NAME = ""

    mock_app_cls = MagicMock()
    app_inst = MagicMock()
    mock_app_cls.return_value = app_inst

    with patch("slack_event_handler.utils.slack_listener.App", mock_app_cls):
        with patch("slack_event_handler.utils.slack_listener.set_slack_app"):
            with patch("slack_event_handler.utils.slack_listener.start_worker"):
                listener = SlackListener(
                    bot_token="xoxb-test",
                    app_token="xapp-test",
                    team_id="T1",
                )

    fid_url = "https://files.slack.com/archives/F0123456789AB"
    assert listener._extract_file_id_from_url(fid_url) == "F0123456789AB"

    assert listener._is_huddle_ai_note_event(
        {"ai_context": {"type": "summary", "summary": {"type": "huddle"}}}
    )
    assert listener._is_huddle_ai_note_event([]) is False

    assert listener._mark_file_processed("FX") is True
    assert listener._mark_file_processed("FX") is False
    listener._unmark_file_processed("FX")
    assert listener._mark_file_processed("FX") is True


@pytest.mark.django_db
def test_slack_listener_resolve_pr_channel(settings, fake_slack_bolt):
    from slack_event_handler.utils.slack_listener import SlackListener

    settings.SLACK_TEAM_SCOPE = {}
    settings.SLACK_PR_BOT_CHANNEL_NAME = "alerts"

    mock_app_cls = MagicMock()
    app_inst = MagicMock()
    app_inst.client.conversations_list.return_value = {
        "channels": [{"name": "alerts", "id": "CALERT"}],
        "response_metadata": {},
    }
    mock_app_cls.return_value = app_inst

    with patch("slack_event_handler.utils.slack_listener.App", mock_app_cls):
        with patch("slack_event_handler.utils.slack_listener.set_slack_app"):
            with patch("slack_event_handler.utils.slack_listener.start_worker"):
                listener = SlackListener(
                    bot_token="xoxb-test",
                    app_token="xapp-test",
                    team_id="T1",
                )
    assert listener._pr_channel_id == "CALERT"


@pytest.mark.django_db
def test_handle_pr_request_invalid_org(settings, fake_slack_bolt):
    from slack_event_handler.utils.slack_listener import SlackListener

    settings.SLACK_TEAM_SCOPE = {}
    settings.SLACK_PR_BOT_CHANNEL_NAME = ""
    settings.SLACK_PR_BOT_TEAM = "boostorg"

    mock_app_cls = MagicMock()
    mock_app_cls.return_value = MagicMock()

    with patch("slack_event_handler.utils.slack_listener.App", mock_app_cls):
        with patch("slack_event_handler.utils.slack_listener.set_slack_app"):
            with patch("slack_event_handler.utils.slack_listener.start_worker"):
                listener = SlackListener(
                    bot_token="xoxb-test",
                    app_token="xapp-test",
                    team_id="T1",
                )

    with patch.object(listener, "_send_user_reply") as send:
        listener._handle_pr_request(
            "https://github.com/other/repo/pull/9",
            "C1",
            "1.0",
            "U1",
            False,
        )
    send.assert_called()


@pytest.mark.django_db
def test_slack_listener_start_calls_socket_handler(settings, fake_slack_bolt):
    from slack_event_handler.utils.slack_listener import SlackListener

    settings.SLACK_TEAM_SCOPE = {}
    settings.SLACK_PR_BOT_CHANNEL_NAME = ""

    mock_app_cls = MagicMock()
    mock_app_cls.return_value = MagicMock()

    with patch("slack_event_handler.utils.slack_listener.App", mock_app_cls):
        with patch("slack_event_handler.utils.slack_listener.set_slack_app"):
            with patch("slack_event_handler.utils.slack_listener.start_worker"):
                listener = SlackListener(
                    bot_token="xoxb-test",
                    app_token="xapp-test",
                    team_id="T1",
                )

    with patch("slack_event_handler.utils.slack_listener.SocketModeHandler") as H:
        handler_inst = MagicMock()
        H.return_value = handler_inst
        listener.start()
    handler_inst.start.assert_called_once()


@pytest.mark.django_db
def test_start_slack_listener_factory(settings, fake_slack_bolt):
    from slack_event_handler.utils import slack_listener as sl

    settings.SLACK_TEAM_SCOPE = {}
    settings.SLACK_PR_BOT_CHANNEL_NAME = ""

    mock_listener = MagicMock()
    with patch.object(sl, "SlackListener", return_value=mock_listener):
        sl.start_slack_listener(bot_token="a", app_token="b", team_id="T")
    mock_listener.start.assert_called_once()
