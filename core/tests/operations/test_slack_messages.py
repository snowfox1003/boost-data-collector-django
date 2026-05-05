"""Tests for core.operations.slack_ops.messages."""

from unittest.mock import MagicMock, patch

from core.operations.slack_ops.messages import get_channel_messages


def test_get_channel_messages_single_page():
    client = MagicMock()
    client.conversations_history.return_value = {
        "ok": True,
        "messages": [{"ts": "1", "text": "hi"}],
        "response_metadata": {},
    }
    out = get_channel_messages("C1", limit=50, client=client)
    assert len(out) == 1
    client.conversations_history.assert_called_once()
    call_kw = client.conversations_history.call_args[1]
    assert call_kw["channel"] == "C1"
    assert call_kw["limit"] == 50
    assert call_kw["cursor"] is None


def test_get_channel_messages_paginates():
    client = MagicMock()
    client.conversations_history.side_effect = [
        {
            "ok": True,
            "messages": [{"ts": "1"}],
            "response_metadata": {"next_cursor": "cur1"},
        },
        {
            "ok": True,
            "messages": [{"ts": "2"}],
            "response_metadata": {},
        },
    ]
    out = get_channel_messages("C9", limit=1000, client=client)
    assert len(out) == 2
    assert client.conversations_history.call_count == 2


def test_get_channel_messages_first_request_not_ok():
    client = MagicMock()
    client.conversations_history.return_value = {"ok": False, "error": "not_in_channel"}
    assert get_channel_messages("C1", client=client) == []


def test_get_channel_messages_api_error_returns_partial():
    client = MagicMock()
    client.conversations_history.side_effect = [
        {"ok": True, "messages": [{"ts": "1"}], "response_metadata": {}},
        {"ok": False, "error": "channel_not_found"},
    ]
    out = get_channel_messages("Cx", client=client)
    assert len(out) == 1


def test_get_channel_messages_empty_batch_stops():
    client = MagicMock()
    client.conversations_history.return_value = {
        "ok": True,
        "messages": [],
        "response_metadata": {"next_cursor": "should_ignore"},
    }
    assert get_channel_messages("C0", client=client) == []


def test_get_channel_messages_uses_default_client():
    client = MagicMock()
    client.conversations_history.return_value = {
        "ok": True,
        "messages": [],
        "response_metadata": {},
    }
    with patch(
        "core.operations.slack_ops.messages.get_slack_client",
        return_value=client,
    ):
        get_channel_messages("Cdef")
    client.conversations_history.assert_called()


def test_get_channel_messages_caps_limit_at_1000():
    client = MagicMock()
    client.conversations_history.return_value = {
        "ok": True,
        "messages": [],
        "response_metadata": {},
    }
    get_channel_messages("C1", limit=5000, client=client)
    assert client.conversations_history.call_args[1]["limit"] == 1000


def test_get_channel_messages_passes_oldest_latest():
    client = MagicMock()
    client.conversations_history.return_value = {
        "ok": True,
        "messages": [],
        "response_metadata": {},
    }
    get_channel_messages("C1", oldest="100.0", latest="200.0", client=client)
    kw = client.conversations_history.call_args[1]
    assert kw["oldest"] == "100.0"
    assert kw["latest"] == "200.0"
