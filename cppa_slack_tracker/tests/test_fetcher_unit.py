"""Unit tests for cppa_slack_tracker.fetcher."""

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from cppa_slack_tracker.fetcher import (
    _ts_to_utc_date,
    fetch_channel_list,
    fetch_channel_user_list,
    fetch_messages,
    fetch_team_info,
    fetch_user_info,
    fetch_user_list,
)


def test_ts_to_utc_date_none_and_invalid():
    assert _ts_to_utc_date(None) is None
    assert _ts_to_utc_date("") is None
    assert _ts_to_utc_date("not-a-float") is None


def test_ts_to_utc_date_ok():
    # Slack ts for a known instant
    d = _ts_to_utc_date("1609459200.000000")  # 2021-01-01 00:00:00 UTC
    assert d == date(2021, 1, 1)


def test_fetch_user_list_paginates():
    client = MagicMock()
    client.users_list.side_effect = [
        {
            "ok": True,
            "members": [{"id": "U1"}],
            "response_metadata": {"next_cursor": "c1"},
        },
        {"ok": True, "members": [{"id": "U2"}], "response_metadata": {}},
    ]
    out = fetch_user_list("T1", client=client)
    assert [m["id"] for m in out] == ["U1", "U2"]


def test_fetch_user_info_ok_and_none():
    client = MagicMock()
    client.users_info.return_value = {"ok": True, "user": {"id": "U1"}}
    assert fetch_user_info("U1", client=client)["id"] == "U1"
    client.users_info.return_value = {"ok": False, "error": "user_not_found"}
    assert fetch_user_info("U9", client=client) is None


def test_fetch_channel_list_error():
    client = MagicMock()
    client.conversations_list.return_value = {"ok": False}
    assert fetch_channel_list("T1", client=client) == []


def test_fetch_messages_history_error():
    client = MagicMock()
    client.conversations_history.return_value = {"ok": False}
    assert (
        fetch_messages(
            "C1",
            date(2021, 1, 1),
            date(2021, 1, 2),
            client=client,
        )
        == []
    )


def test_fetch_user_list_error_stops():
    client = MagicMock()
    client.users_list.return_value = {"ok": False, "error": "ratelimited"}
    assert fetch_user_list("T1", client=client) == []


def test_fetch_team_info_team_info_ok():
    client = MagicMock()
    client.team_info.return_value = {
        "ok": True,
        "team": {"id": "T9", "name": "My Team"},
    }
    team = fetch_team_info(team_id="T9", client=client)
    assert team["name"] == "My Team"


def test_fetch_team_info_auth_test_fallback():
    client = MagicMock()
    client.team_info.return_value = {"ok": False}
    client.auth_test.return_value = {
        "ok": True,
        "team_id": "T1",
        "team": "Fallback Name",
    }
    team = fetch_team_info(team_id="T1", client=client)
    assert team == {"id": "T1", "name": "Fallback Name"}


def test_fetch_team_info_auth_test_team_id_mismatch():
    client = MagicMock()
    client.team_info.return_value = {"ok": False}
    client.auth_test.return_value = {
        "ok": True,
        "team_id": "OTHER",
        "team": "X",
    }
    assert fetch_team_info(team_id="T1", client=client) is None


def test_fetch_team_info_auth_test_fails():
    client = MagicMock()
    client.team_info.return_value = {"ok": False}
    client.auth_test.return_value = {"ok": False, "error": "invalid_auth"}
    assert fetch_team_info(client=client) is None


def test_fetch_messages_with_start_date_filters():
    client = MagicMock()
    client.conversations_history.return_value = {
        "ok": True,
        "messages": [
            {"ts": "1609459200.000000", "text": "in range"},
            {"ts": "1577836800.000000", "text": "too old"},
            {
                "ts": "1577836800.000000",
                "edited": {"ts": "1609545600.000000"},
                "text": "edited in range",
            },
        ],
        "response_metadata": {},
    }
    start = date(2021, 1, 1)
    end = date(2021, 1, 31)
    msgs = fetch_messages("C1", start, end, client=client)
    texts = {m["text"] for m in msgs}
    assert "in range" in texts
    assert "edited in range" in texts
    assert "too old" not in texts


def test_fetch_messages_no_start_includes_old_until_end():
    client = MagicMock()
    client.conversations_history.return_value = {
        "ok": True,
        "messages": [
            {"ts": "1577836800.000000", "text": "old"},
        ],
        "response_metadata": {},
    }
    end = date(2021, 1, 31)
    msgs = fetch_messages("C1", None, end, client=client)
    assert len(msgs) == 1


def test_fetch_messages_datetime_end_normalized():
    client = MagicMock()
    client.conversations_history.return_value = {
        "ok": True,
        "messages": [],
        "response_metadata": {},
    }
    end_dt = datetime(2021, 1, 15, 12, 0, tzinfo=timezone.utc)
    fetch_messages("C1", None, end_dt, client=client)
    kw = client.conversations_history.call_args[1]
    assert "latest" in kw


def test_fetch_channel_user_list_raises_on_error():
    client = MagicMock()
    client.conversations_members.return_value = {
        "ok": False,
        "error": "channel_not_found",
    }
    with pytest.raises(RuntimeError, match="conversations.members failed"):
        fetch_channel_user_list("C404", client=client)


@patch("cppa_slack_tracker.fetcher.get_slack_client")
def test_fetch_user_list_uses_default_client(mock_get):
    client = MagicMock()
    client.users_list.return_value = {
        "ok": True,
        "members": [],
        "response_metadata": {},
    }
    mock_get.return_value = client
    fetch_user_list("T1")
    mock_get.assert_called_once_with(team_id="T1")
