# ruff: noqa: S106 -- synthetic Slack tokens in tests.
"""Extra coverage for slack_event_handler.utils.slack_listener."""

from unittest.mock import MagicMock, patch

import pytest

from slack_event_handler.tests.conftest import ImmediateThread

SCOPE_HUDDLE = 0
SCOPE_PR_BOT = 1


def _bolt_app_inst(**kwargs):
    """Magic Slack App instance with .event usable as a Bolt decorator."""
    app_inst = MagicMock(**kwargs)

    def event_register(spec):
        def deco(fn):
            return fn

        return deco

    app_inst.event = event_register
    return app_inst


def _bolt_app_mock_with_inst(app_inst):
    mock_app_cls = MagicMock()
    mock_app_cls.return_value = app_inst
    return mock_app_cls


@pytest.mark.django_db
def test_slack_listener_raises_when_bot_token_missing(fake_slack_bolt):
    from slack_event_handler.utils.slack_listener import SlackListener

    with pytest.raises(ValueError, match="Missing bot_token"):
        SlackListener(bot_token="", app_token="xapp-test")


@pytest.mark.django_db
def test_slack_listener_raises_when_app_token_missing(settings, fake_slack_bolt):
    from slack_event_handler.utils.slack_listener import SlackListener

    settings.SLACK_TEAM_SCOPE = {}
    settings.SLACK_PR_BOT_CHANNEL_NAME = ""

    mock_app_cls = MagicMock()
    mock_app_cls.return_value = MagicMock()

    with patch("slack_event_handler.utils.slack_listener.App", mock_app_cls):
        with patch("slack_event_handler.utils.slack_listener.set_slack_app"):
            with patch("slack_event_handler.utils.slack_listener.start_worker"):
                with patch(
                    "slack_event_handler.utils.slack_listener.get_slack_app_token",
                    return_value="",
                ):
                    with pytest.raises(ValueError, match="SLACK_APP_TOKEN"):
                        SlackListener(
                            bot_token="xoxb-test",
                            app_token="",
                            team_id="T1",
                        )


@pytest.mark.django_db
def test_resolve_pr_channel_not_found_logs(settings, fake_slack_bolt):
    from slack_event_handler.utils.slack_listener import SlackListener

    settings.SLACK_TEAM_SCOPE = {}
    settings.SLACK_PR_BOT_CHANNEL_NAME = "missing-channel"

    app_inst = _bolt_app_inst()
    app_inst.client.conversations_list.return_value = {
        "channels": [{"name": "other", "id": "C1"}],
        "response_metadata": {},
    }
    mock_app_cls = _bolt_app_mock_with_inst(app_inst)

    with patch("slack_event_handler.utils.slack_listener.App", mock_app_cls):
        with patch("slack_event_handler.utils.slack_listener.set_slack_app"):
            with patch("slack_event_handler.utils.slack_listener.start_worker"):
                listener = SlackListener(
                    bot_token="xoxb-test",
                    app_token="xapp-test",
                    team_id="T1",
                )
    assert listener._pr_channel_id is None


@pytest.mark.django_db
def test_resolve_pr_channel_pagination(settings, fake_slack_bolt):
    from slack_event_handler.utils.slack_listener import SlackListener

    settings.SLACK_TEAM_SCOPE = {}
    settings.SLACK_PR_BOT_CHANNEL_NAME = "alerts"

    app_inst = _bolt_app_inst()
    app_inst.client.conversations_list.side_effect = [
        {
            "channels": [{"name": "other", "id": "x"}],
            "response_metadata": {"next_cursor": "c1"},
        },
        {
            "channels": [{"name": "alerts", "id": "CAL"}],
            "response_metadata": {},
        },
    ]
    mock_app_cls = _bolt_app_mock_with_inst(app_inst)

    with patch("slack_event_handler.utils.slack_listener.App", mock_app_cls):
        with patch("slack_event_handler.utils.slack_listener.set_slack_app"):
            with patch("slack_event_handler.utils.slack_listener.start_worker"):
                listener = SlackListener(
                    bot_token="xoxb-test",
                    app_token="xapp-test",
                    team_id="T1",
                )
    assert listener._pr_channel_id == "CAL"


@pytest.mark.django_db
def test_resolve_pr_channel_api_error(settings, fake_slack_bolt):
    from slack_event_handler.utils.slack_listener import SlackListener

    settings.SLACK_TEAM_SCOPE = {}
    settings.SLACK_PR_BOT_CHANNEL_NAME = "alerts"

    app_inst = _bolt_app_inst()
    app_inst.client.conversations_list.side_effect = OSError("api down")
    mock_app_cls = _bolt_app_mock_with_inst(app_inst)

    with patch("slack_event_handler.utils.slack_listener.App", mock_app_cls):
        with patch("slack_event_handler.utils.slack_listener.set_slack_app"):
            with patch("slack_event_handler.utils.slack_listener.start_worker"):
                listener = SlackListener(
                    bot_token="xoxb-test",
                    app_token="xapp-test",
                    team_id="T1",
                )
    assert listener._pr_channel_id is None


@pytest.mark.django_db
def test_send_user_reply_channel_and_dm(settings, fake_slack_bolt):
    from slack_event_handler.utils.slack_listener import SlackListener

    settings.SLACK_TEAM_SCOPE = {}
    settings.SLACK_PR_BOT_CHANNEL_NAME = ""

    app_inst = _bolt_app_inst()
    mock_app_cls = _bolt_app_mock_with_inst(app_inst)

    with patch("slack_event_handler.utils.slack_listener.App", mock_app_cls):
        with patch("slack_event_handler.utils.slack_listener.set_slack_app"):
            with patch("slack_event_handler.utils.slack_listener.start_worker"):
                listener = SlackListener(
                    bot_token="xoxb-test",
                    app_token="xapp-test",
                    team_id="T1",
                )

    listener._send_user_reply("C1", "9.9", False, "hi")
    kwargs = app_inst.client.chat_postMessage.call_args.kwargs
    assert kwargs["thread_ts"] == "9.9"

    app_inst.client.chat_postMessage.side_effect = RuntimeError("fail")
    listener._send_user_reply("D1", "9.9", True, "dm")


@pytest.mark.django_db
def test_handle_pr_request_no_github_url(settings, fake_slack_bolt):
    from slack_event_handler.utils.slack_listener import SlackListener

    settings.SLACK_TEAM_SCOPE = {}
    settings.SLACK_PR_BOT_CHANNEL_NAME = ""
    settings.SLACK_PR_BOT_TEAM = ""

    mock_app_cls = _bolt_app_mock_with_inst(_bolt_app_inst())

    with patch("slack_event_handler.utils.slack_listener.App", mock_app_cls):
        with patch("slack_event_handler.utils.slack_listener.set_slack_app"):
            with patch("slack_event_handler.utils.slack_listener.start_worker"):
                listener = SlackListener(
                    bot_token="xoxb-test",
                    app_token="xapp-test",
                    team_id="T1",
                )

    with patch.object(listener, "_send_user_reply") as send:
        listener._handle_pr_request("hello no urls", "C1", "1", "U1", False)
    send.assert_called_once()
    assert "No GitHub PR URL" in send.call_args[0][3]


def _bolt_app_mock():
    return _bolt_app_mock_with_inst(_bolt_app_inst())


@pytest.mark.django_db
def test_handle_pr_request_enqueues_once_per_pr(settings, fake_slack_bolt):
    import slack_event_handler.utils.slack_listener as sl_mod

    from slack_event_handler.utils.slack_listener import SlackListener

    settings.SLACK_TEAM_SCOPE = {}
    settings.SLACK_PR_BOT_CHANNEL_NAME = ""
    settings.SLACK_PR_BOT_TEAM = ""

    mock_app_cls = _bolt_app_mock()

    with patch.object(sl_mod, "App", mock_app_cls):
        with patch.object(sl_mod, "set_slack_app"):
            with patch.object(sl_mod, "start_worker"):
                listener = SlackListener(
                    bot_token="xoxb-test",
                    app_token="xapp-test",
                    team_id="T1",
                )

    url = "https://github.com/acme/r/pull/3"
    text = f"{url} {url}"

    with patch.object(listener, "_send_user_reply"):
        with patch.object(sl_mod, "enqueue_job") as eq:
            with patch.object(sl_mod, "estimated_delay_sec", return_value=0):
                listener._handle_pr_request(text, "C1", "1", "U1", False)
    assert eq.call_count == 1


@pytest.mark.django_db
def test_handle_pr_request_rate_limit_ack(settings, fake_slack_bolt):
    import slack_event_handler.utils.slack_listener as sl_mod

    from slack_event_handler.utils.slack_listener import SlackListener

    settings.SLACK_TEAM_SCOPE = {}
    settings.SLACK_PR_BOT_CHANNEL_NAME = ""
    settings.SLACK_PR_BOT_TEAM = ""

    mock_app_cls = _bolt_app_mock()

    with patch.object(sl_mod, "App", mock_app_cls):
        with patch.object(sl_mod, "set_slack_app"):
            with patch.object(sl_mod, "start_worker"):
                listener = SlackListener(
                    bot_token="xoxb-test",
                    app_token="xapp-test",
                    team_id="T1",
                )

    with patch.object(listener, "_send_user_reply") as send:
        with patch.object(sl_mod, "enqueue_job"):
            with patch.object(sl_mod, "estimated_delay_sec", return_value=30):
                listener._handle_pr_request(
                    "https://github.com/acme/r/pull/1",
                    "C1",
                    "1",
                    "U1",
                    False,
                )
    ack = send.call_args[0][3]
    assert "30s" in ack


@pytest.mark.django_db
def test_extract_file_id_from_url_regex_error(settings, fake_slack_bolt):
    from slack_event_handler.utils.slack_listener import SlackListener

    settings.SLACK_TEAM_SCOPE = {}
    settings.SLACK_PR_BOT_CHANNEL_NAME = ""

    mock_app_cls = _bolt_app_mock_with_inst(_bolt_app_inst())

    with patch("slack_event_handler.utils.slack_listener.App", mock_app_cls):
        with patch("slack_event_handler.utils.slack_listener.set_slack_app"):
            with patch("slack_event_handler.utils.slack_listener.start_worker"):
                listener = SlackListener(
                    bot_token="xoxb-test",
                    app_token="xapp-test",
                    team_id="T1",
                )

    with patch(
        "slack_event_handler.utils.slack_listener.re.search",
        side_effect=RuntimeError("regex"),
    ):
        assert listener._extract_file_id_from_url("https://x/F0123456789AB") is None


@pytest.mark.django_db
def test_extract_file_id_from_event_finds_view_ai_notes(settings, fake_slack_bolt):
    from slack_event_handler.utils.slack_listener import SlackListener

    settings.SLACK_TEAM_SCOPE = {}
    settings.SLACK_PR_BOT_CHANNEL_NAME = ""

    mock_app_cls = _bolt_app_mock_with_inst(_bolt_app_inst())

    with patch("slack_event_handler.utils.slack_listener.App", mock_app_cls):
        with patch("slack_event_handler.utils.slack_listener.set_slack_app"):
            with patch("slack_event_handler.utils.slack_listener.start_worker"):
                listener = SlackListener(
                    bot_token="xoxb-test",
                    app_token="xapp-test",
                    team_id="T1",
                )

    event = {
        "blocks": [
            {
                "elements": [
                    {
                        "type": "rich_text_section",
                        "elements": [
                            {
                                "type": "link",
                                "text": "View AI notes",
                                "url": "https://files.slack.com/archives/F09999999999",
                            }
                        ],
                    }
                ]
            }
        ]
    }
    assert listener._extract_file_id_from_event(event) == "F09999999999"


@pytest.mark.django_db
def test_mark_file_processed_evicts_oldest(settings, fake_slack_bolt):
    import slack_event_handler.utils.slack_listener as sl_mod

    from slack_event_handler.utils.slack_listener import SlackListener

    settings.SLACK_TEAM_SCOPE = {}
    settings.SLACK_PR_BOT_CHANNEL_NAME = ""

    mock_app_cls = _bolt_app_mock()

    with patch.object(sl_mod, "MAX_PROCESSED_FILE_IDS", 2):
        with patch.object(sl_mod, "App", mock_app_cls):
            with patch.object(sl_mod, "set_slack_app"):
                with patch.object(sl_mod, "start_worker"):
                    listener = SlackListener(
                        bot_token="xoxb-test",
                        app_token="xapp-test",
                        team_id="T1",
                    )
                    assert listener._mark_file_processed("FA") is True
                    assert listener._mark_file_processed("FB") is True
                    assert listener._mark_file_processed("FC") is True
                    assert "FA" not in listener._processed_file_ids


@pytest.mark.django_db
def test_message_handler_huddle_success_sync(settings, fake_slack_bolt):
    from slack_event_handler.utils.slack_listener import SlackListener

    settings.SLACK_TEAM_SCOPE = {"T1": [SCOPE_HUDDLE]}
    settings.SLACK_PR_BOT_CHANNEL_NAME = ""

    mock_app_cls = MagicMock()
    app_inst = MagicMock()
    captured = []

    def event_register(spec):
        def deco(fn):
            captured.append((spec, fn))
            return fn

        return deco

    app_inst.event = event_register
    mock_app_cls.return_value = app_inst

    event_body = {
        "ai_context": {"type": "summary", "summary": {"type": "huddle"}},
        "blocks": [
            {
                "elements": [
                    {
                        "type": "rich_text_section",
                        "elements": [
                            {
                                "type": "link",
                                "text": "View AI notes",
                                "url": "https://files.slack.com/archives/F08888888888",
                            }
                        ],
                    }
                ]
            }
        ],
    }

    with patch(
        "slack_event_handler.utils.slack_listener.threading.Thread", ImmediateThread
    ):
        with patch("slack_event_handler.utils.slack_listener.time.sleep"):
            with patch(
                "slack_event_handler.utils.huddle_processor.process_huddle_canvas",
                return_value={"success": True, "github_url": "https://g/pr/1"},
            ):
                with patch(
                    "slack_event_handler.utils.slack_listener.App", mock_app_cls
                ):
                    with patch(
                        "slack_event_handler.utils.slack_listener.set_slack_app"
                    ):
                        with patch(
                            "slack_event_handler.utils.slack_listener.start_worker"
                        ):
                            SlackListener(
                                bot_token="xoxb-test",
                                app_token="xapp-test",
                                team_id="T1",
                            )
                            msg_fn = next(
                                fn for spec, fn in captured if spec == "message"
                            )
                            msg_fn(event_body, {"event": event_body})


@pytest.mark.django_db
def test_message_handler_huddle_failure_unmarks(settings, fake_slack_bolt):
    from slack_event_handler.utils.slack_listener import SlackListener

    settings.SLACK_TEAM_SCOPE = {"T1": [SCOPE_HUDDLE]}
    settings.SLACK_PR_BOT_CHANNEL_NAME = ""

    mock_app_cls = MagicMock()
    app_inst = MagicMock()
    captured = []

    def event_register(spec):
        def deco(fn):
            captured.append((spec, fn))
            return fn

        return deco

    app_inst.event = event_register
    mock_app_cls.return_value = app_inst

    event_body = {
        "ai_context": {"type": "summary", "summary": {"type": "huddle"}},
        "blocks": [
            {
                "elements": [
                    {
                        "type": "rich_text_section",
                        "elements": [
                            {
                                "type": "link",
                                "text": "View AI note",
                                "url": "https://files.slack.com/archives/F07777777777",
                            }
                        ],
                    }
                ]
            }
        ],
    }

    with patch(
        "slack_event_handler.utils.slack_listener.threading.Thread", ImmediateThread
    ):
        with patch("slack_event_handler.utils.slack_listener.time.sleep"):
            with patch(
                "slack_event_handler.utils.huddle_processor.process_huddle_canvas",
                return_value={"success": False},
            ):
                with patch(
                    "slack_event_handler.utils.slack_listener.App", mock_app_cls
                ):
                    with patch(
                        "slack_event_handler.utils.slack_listener.set_slack_app"
                    ):
                        with patch(
                            "slack_event_handler.utils.slack_listener.start_worker"
                        ):
                            listener = SlackListener(
                                bot_token="xoxb-test",
                                app_token="xapp-test",
                                team_id="T1",
                            )
                            msg_fn = next(
                                fn for spec, fn in captured if spec == "message"
                            )
                            msg_fn(event_body, {"event": event_body})
                            assert "F07777777777" not in listener._processed_file_ids


@pytest.mark.django_db
def test_message_handler_huddle_process_exception_unmarks(settings, fake_slack_bolt):
    from slack_event_handler.utils.slack_listener import SlackListener

    settings.SLACK_TEAM_SCOPE = {"T1": [SCOPE_HUDDLE]}
    settings.SLACK_PR_BOT_CHANNEL_NAME = ""

    mock_app_cls = MagicMock()
    app_inst = MagicMock()
    captured = []

    def event_register(spec):
        def deco(fn):
            captured.append((spec, fn))
            return fn

        return deco

    app_inst.event = event_register
    mock_app_cls.return_value = app_inst

    event_body = {
        "ai_context": {"type": "summary", "summary": {"type": "huddle"}},
        "blocks": [
            {
                "elements": [
                    {
                        "type": "rich_text_section",
                        "elements": [
                            {
                                "type": "link",
                                "text": "View AI notes",
                                "url": "https://files.slack.com/archives/F06666666666",
                            }
                        ],
                    }
                ]
            }
        ],
    }

    with patch(
        "slack_event_handler.utils.slack_listener.threading.Thread", ImmediateThread
    ):
        with patch("slack_event_handler.utils.slack_listener.time.sleep"):
            with patch(
                "slack_event_handler.utils.huddle_processor.process_huddle_canvas",
                side_effect=RuntimeError("proc"),
            ):
                with patch(
                    "slack_event_handler.utils.slack_listener.App", mock_app_cls
                ):
                    with patch(
                        "slack_event_handler.utils.slack_listener.set_slack_app"
                    ):
                        with patch(
                            "slack_event_handler.utils.slack_listener.start_worker"
                        ):
                            listener = SlackListener(
                                bot_token="xoxb-test",
                                app_token="xapp-test",
                                team_id="T1",
                            )
                            msg_fn = next(
                                fn for spec, fn in captured if spec == "message"
                            )
                            msg_fn(event_body, {"event": event_body})
                            assert "F06666666666" not in listener._processed_file_ids


@pytest.mark.django_db
def test_message_handler_huddle_missing_file_id_returns(settings, fake_slack_bolt):
    from slack_event_handler.utils.slack_listener import SlackListener

    settings.SLACK_TEAM_SCOPE = {"T1": [SCOPE_HUDDLE]}
    settings.SLACK_PR_BOT_CHANNEL_NAME = ""

    mock_app_cls = MagicMock()
    app_inst = MagicMock()
    captured = []

    def event_register(spec):
        def deco(fn):
            captured.append((spec, fn))
            return fn

        return deco

    app_inst.event = event_register
    mock_app_cls.return_value = app_inst

    event_body = {
        "ai_context": {"type": "summary", "summary": {"type": "huddle"}},
        "blocks": [],
    }

    with patch("slack_event_handler.utils.slack_listener.App", mock_app_cls):
        with patch("slack_event_handler.utils.slack_listener.set_slack_app"):
            with patch("slack_event_handler.utils.slack_listener.start_worker"):
                SlackListener(
                    bot_token="xoxb-test",
                    app_token="xapp-test",
                    team_id="T1",
                )

    msg_fn = next(fn for spec, fn in captured if spec == "message")
    msg_fn(event_body, {"event": event_body})


@pytest.mark.django_db
def test_message_handler_pr_channel_match(settings, fake_slack_bolt):
    from slack_event_handler.utils.slack_listener import SlackListener

    settings.SLACK_TEAM_SCOPE = {"T1": [SCOPE_PR_BOT]}
    settings.SLACK_PR_BOT_CHANNEL_NAME = ""
    settings.SLACK_PR_BOT_TEAM = ""

    mock_app_cls = MagicMock()
    app_inst = MagicMock()
    captured = []

    def event_register(spec):
        def deco(fn):
            captured.append((spec, fn))
            return fn

        return deco

    app_inst.event = event_register
    mock_app_cls.return_value = app_inst

    with patch("slack_event_handler.utils.slack_listener.App", mock_app_cls):
        with patch("slack_event_handler.utils.slack_listener.set_slack_app"):
            with patch("slack_event_handler.utils.slack_listener.start_worker"):
                listener = SlackListener(
                    bot_token="xoxb-test",
                    app_token="xapp-test",
                    team_id="T1",
                )

    listener._pr_channel_id = "CPR"

    msg_fn = next(fn for spec, fn in captured if spec == "message")
    with patch.object(listener, "_handle_pr_request") as hp:
        msg_fn(
            {
                "channel_type": "channel",
                "text": "https://github.com/acme/r/pull/1",
                "channel": "CPR",
                "ts": "1",
                "user": "U1",
            },
            {},
        )
        hp.assert_called_once()


@pytest.mark.django_db
def test_message_handler_neither_huddle_nor_pr_channel(settings, fake_slack_bolt):
    from slack_event_handler.utils.slack_listener import SlackListener

    settings.SLACK_TEAM_SCOPE = {"T1": [SCOPE_PR_BOT]}
    settings.SLACK_PR_BOT_CHANNEL_NAME = ""
    settings.SLACK_PR_BOT_TEAM = ""

    mock_app_cls = MagicMock()
    app_inst = MagicMock()
    captured = []

    def event_register(spec):
        def deco(fn):
            captured.append((spec, fn))
            return fn

        return deco

    app_inst.event = event_register
    mock_app_cls.return_value = app_inst

    with patch("slack_event_handler.utils.slack_listener.App", mock_app_cls):
        with patch("slack_event_handler.utils.slack_listener.set_slack_app"):
            with patch("slack_event_handler.utils.slack_listener.start_worker"):
                listener = SlackListener(
                    bot_token="xoxb-test",
                    app_token="xapp-test",
                    team_id="T1",
                )

    listener._pr_channel_id = "CPR"

    msg_fn = next(fn for spec, fn in captured if spec == "message")
    with patch.object(listener, "_handle_pr_request") as hp:
        msg_fn(
            {
                "channel_type": "channel",
                "text": "hello",
                "channel": "COTHER",
                "ts": "1",
                "user": "U1",
            },
            {},
        )
        hp.assert_not_called()


@pytest.mark.django_db
def test_is_huddle_ai_note_malformed_logs(settings, fake_slack_bolt):
    from slack_event_handler.utils.slack_listener import SlackListener

    settings.SLACK_TEAM_SCOPE = {}
    settings.SLACK_PR_BOT_CHANNEL_NAME = ""

    mock_app_cls = _bolt_app_mock_with_inst(_bolt_app_inst())

    with patch("slack_event_handler.utils.slack_listener.App", mock_app_cls):
        with patch("slack_event_handler.utils.slack_listener.set_slack_app"):
            with patch("slack_event_handler.utils.slack_listener.start_worker"):
                listener = SlackListener(
                    bot_token="xoxb-test",
                    app_token="xapp-test",
                    team_id="T1",
                )

    class BadDict(dict):
        def get(self, key, default=None):
            if key == "ai_context":
                raise RuntimeError("bad")
            return super().get(key, default)

    assert listener._is_huddle_ai_note_event(BadDict()) is False
