"""Exercise slack_listener registered event handlers (Bolt mocked)."""

from unittest.mock import MagicMock, patch

import pytest

# Mirror slack_listener team-scope constants (avoid importing slack_listener at collect time).
SCOPE_HUDDLE = 0
SCOPE_PR_BOT = 1


@pytest.mark.django_db
def test_message_handler_skips_subtypes(settings, fake_slack_bolt):
    from slack_event_handler.utils.slack_listener import SlackListener

    settings.SLACK_TEAM_SCOPE = {}
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

    with patch("slack_event_handler.utils.slack_listener.App", mock_app_cls):
        with patch("slack_event_handler.utils.slack_listener.set_slack_app"):
            with patch("slack_event_handler.utils.slack_listener.start_worker"):
                SlackListener(
                    bot_token="xoxb-test", app_token="xapp-test", team_id="T1"
                )

    msg_fn = next(fn for spec, fn in captured if spec == "message")
    msg_fn({"subtype": "message_changed"}, {})
    msg_fn({"subtype": "message_deleted"}, {})


@pytest.mark.django_db
def test_message_handler_pr_branch(settings, fake_slack_bolt):
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

    msg_fn = next(fn for spec, fn in captured if spec == "message")
    with patch.object(listener, "_handle_pr_request") as hp:
        msg_fn(
            {
                "channel_type": "im",
                "text": "hello",
                "channel": "D1",
                "ts": "1",
                "user": "U1",
            },
            {},
        )
        hp.assert_called_once()


@pytest.mark.django_db
def test_message_handler_pr_disabled_scope_logs(settings, fake_slack_bolt):
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

    with patch("slack_event_handler.utils.slack_listener.App", mock_app_cls):
        with patch("slack_event_handler.utils.slack_listener.set_slack_app"):
            with patch("slack_event_handler.utils.slack_listener.start_worker"):
                SlackListener(
                    bot_token="xoxb-test", app_token="xapp-test", team_id="T1"
                )

    msg_fn = next(fn for spec, fn in captured if spec == "message")
    msg_fn(
        {
            "channel_type": "channel",
            "text": "hi",
            "channel": "C99",
            "ts": "1",
        },
        {},
    )


@pytest.mark.django_db
def test_misc_event_handlers_run(settings, fake_slack_bolt):
    from slack_event_handler.utils.slack_listener import SlackListener

    settings.SLACK_TEAM_SCOPE = {}
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

    with patch("slack_event_handler.utils.slack_listener.App", mock_app_cls):
        with patch("slack_event_handler.utils.slack_listener.set_slack_app"):
            with patch("slack_event_handler.utils.slack_listener.start_worker"):
                SlackListener(
                    bot_token="xoxb-test", app_token="xapp-test", team_id="T1"
                )

    by_str = {spec: fn for spec, fn in captured if isinstance(spec, str)}
    cb_fn = next(fn for spec, fn in captured if isinstance(spec, dict))

    by_str["file_shared"]({}, {})
    by_str["reaction_added"]({}, {})
    by_str["app_mention"]({}, {})

    cb_fn({}, {"event": {"type": "unknown"}})
