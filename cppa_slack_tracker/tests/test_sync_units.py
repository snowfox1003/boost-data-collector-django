"""Unit tests for cppa_slack_tracker.sync modules (mocked API / DB edges)."""

import json
import uuid
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from cppa_slack_tracker.sync.sync_channel import (
    sync_team,
    sync_channels,
    _process_channel_info,
)
from cppa_slack_tracker.sync.sync_channel_user import (
    get_channels_to_sync,
    sync_channel_users,
)
from cppa_slack_tracker.sync.sync_message import (
    _merge_messages_by_ts,
    _messages_by_day,
    _process_workspace_jsons,
    _ts_to_date,
    sync_messages,
)
from cppa_slack_tracker.sync.sync_user import sync_users, _process_user_info


@pytest.mark.django_db
def test_sync_team_uses_fetched_name(db):
    tid = "T" + uuid.uuid4().hex[:10]
    with patch(
        "cppa_slack_tracker.sync.sync_channel.fetch_team_info",
        return_value={"id": tid, "name": "Fetched"},
    ):
        team = sync_team(tid, team_name=tid)
    assert team.team_name == "Fetched"


@pytest.mark.django_db
def test_sync_team_fetch_exception_falls_back(db):
    tid = "T" + uuid.uuid4().hex[:10]
    with patch(
        "cppa_slack_tracker.sync.sync_channel.fetch_team_info",
        side_effect=RuntimeError("network"),
    ):
        team = sync_team(tid, team_name=None)
    assert team.team_id == tid


@pytest.mark.django_db
def test_sync_team_fetch_mismatched_id_keeps_placeholder(db):
    tid = "T" + uuid.uuid4().hex[:10]
    with patch(
        "cppa_slack_tracker.sync.sync_channel.fetch_team_info",
        return_value={"id": "OTHER", "name": "X"},
    ):
        team = sync_team(tid, team_name=tid)
    assert team.team_name == tid


@pytest.mark.django_db
def test_process_channel_info_missing_id():
    team = MagicMock()
    assert _process_channel_info({}, team) is False


@pytest.mark.django_db
def test_sync_channels_single_conversations_info_ok(
    sample_slack_team,
    sample_slack_channel_data,
):
    mock_client = MagicMock()
    mock_client.conversations_info.return_value = {
        "ok": True,
        "channel": sample_slack_channel_data,
    }
    mock_ch = MagicMock()
    with patch(
        "core.operations.slack_ops.tokens.get_slack_client",
        return_value=mock_client,
    ), patch(
        "cppa_slack_tracker.sync.sync_channel.get_or_create_slack_channel",
        return_value=(mock_ch, True),
    ):
        ok, err = sync_channels(
            sample_slack_team,
            channel_id=sample_slack_channel_data["id"],
            team_id=sample_slack_team.team_id,
        )
    assert ok >= 1 and err == 0


@pytest.mark.django_db
def test_sync_channels_single_not_ok(sample_slack_team):
    mock_client = MagicMock()
    mock_client.conversations_info.return_value = {"ok": False, "error": "not_found"}
    with patch(
        "core.operations.slack_ops.tokens.get_slack_client",
        return_value=mock_client,
    ):
        ok, err = sync_channels(
            sample_slack_team, channel_id="Cmissing", team_id=sample_slack_team.team_id
        )
    assert ok == 0 and err == 1


@pytest.mark.django_db
def test_sync_channels_single_client_raises(sample_slack_team):
    mock_client = MagicMock()
    mock_client.conversations_info.side_effect = RuntimeError("boom")
    with patch(
        "core.operations.slack_ops.tokens.get_slack_client",
        return_value=mock_client,
    ):
        ok, err = sync_channels(
            sample_slack_team, channel_id="C1", team_id=sample_slack_team.team_id
        )
    assert ok == 0 and err == 1


@pytest.mark.django_db
def test_sync_channels_list_fetch_raises(sample_slack_team):
    with patch(
        "cppa_slack_tracker.sync.sync_channel.fetch_channel_list",
        side_effect=RuntimeError("list fail"),
    ):
        ok, err = sync_channels(sample_slack_team, team_id=sample_slack_team.team_id)
    assert ok == 0 and err == 1


@pytest.mark.django_db
def test_sync_channels_list_malformed_and_ok(
    sample_slack_team, sample_slack_channel_data
):
    mock_ch = MagicMock()
    with patch(
        "cppa_slack_tracker.sync.sync_channel.fetch_channel_list",
        return_value=["bad", sample_slack_channel_data],
    ), patch(
        "cppa_slack_tracker.sync.sync_channel.get_or_create_slack_channel",
        return_value=(mock_ch, True),
    ):
        ok, err = sync_channels(sample_slack_team, team_id=sample_slack_team.team_id)
    assert err >= 1
    assert ok >= 1


@pytest.mark.django_db
def test_sync_users_missing_team_id():
    ok, err = sync_users("slug", team_id="")
    assert ok == 0 and err == 1


@pytest.mark.django_db
def test_sync_users_fetch_raises():
    with patch(
        "cppa_slack_tracker.sync.sync_user.fetch_user_list",
        side_effect=RuntimeError("x"),
    ):
        ok, err = sync_users("slug", team_id="T1")
    assert ok == 0 and err == 1


@pytest.mark.django_db
def test_sync_users_malformed_payload():
    with patch(
        "cppa_slack_tracker.sync.sync_user.fetch_user_list",
        return_value=["not-a-dict"],
    ):
        _ok, err = sync_users("slug", team_id="T1")
    assert err >= 1


@pytest.mark.django_db
def test_process_user_info_skip_bot():
    assert _process_user_info({"id": "B1", "is_bot": True}, include_bots=False) is False


@pytest.mark.django_db
def test_get_channels_to_sync_specific(sample_slack_team, sample_slack_channel):
    chs = get_channels_to_sync(
        sample_slack_team, channel_id=sample_slack_channel.channel_id
    )
    assert len(chs) == 1


@pytest.mark.django_db
def test_get_channels_to_sync_unknown_id_returns_all(
    sample_slack_team,
    sample_slack_channel,
):
    chs = get_channels_to_sync(sample_slack_team, channel_id="Cnone")
    assert len(chs) >= 1


@pytest.mark.django_db
def test_sync_channel_users_ok(sample_slack_team, sample_slack_channel):
    with patch(
        "cppa_slack_tracker.sync.sync_channel_user.fetch_channel_user_list",
        return_value=["U1"],
    ), patch(
        "cppa_slack_tracker.sync.sync_channel_user.sync_channel_memberships",
    ) as m_sync:
        ok, err = sync_channel_users(
            sample_slack_team, channel_id=sample_slack_channel.channel_id
        )
    assert ok == 1 and err == 0
    m_sync.assert_called()


@pytest.mark.django_db
def test_sync_channel_users_fetch_fails(sample_slack_team, sample_slack_channel):
    with patch(
        "cppa_slack_tracker.sync.sync_channel_user.fetch_channel_user_list",
        side_effect=RuntimeError("members"),
    ):
        ok, err = sync_channel_users(
            sample_slack_team, channel_id=sample_slack_channel.channel_id
        )
    assert ok == 0 and err == 1


def test_ts_to_date_sync_message():
    assert _ts_to_date(None) is None
    assert _ts_to_date("not") is None


def test_messages_by_day_edited_duplicate_day():
    start = date(2021, 1, 1)
    end = date(2021, 1, 31)
    msgs = [
        {
            "ts": "1609545600.0",
            "edited": {"ts": "1609632000.0"},
        }
    ]
    by_d = _messages_by_day(msgs, start, end)
    assert by_d


def test_messages_by_day_skips_non_dict():
    assert _messages_by_day(["x"], date(2020, 1, 1), date(2030, 1, 1)) == {}


def test_merge_messages_by_ts_orders():
    merged = _merge_messages_by_ts(
        [{"ts": "2", "a": 1}],
        [{"ts": "1", "b": 2}, {"ts": "2", "a": 9}],
    )
    assert [m["ts"] for m in merged] == ["1", "2"]
    assert merged[1]["a"] == 9


@pytest.mark.django_db
def test_process_workspace_jsons_not_list(tmp_path, sample_slack_channel, monkeypatch):
    monkeypatch.setattr(
        "cppa_slack_tracker.sync.sync_message.iter_existing_message_jsons",
        lambda **_: iter([tmp_path / "x.json"]),
    )
    p = tmp_path / "x.json"
    p.write_text('{"not":"list"}', encoding="utf-8")
    s, _e = _process_workspace_jsons(sample_slack_channel)
    assert not p.exists()
    assert s == 0


@pytest.mark.django_db
def test_sync_messages_start_after_end(sample_slack_channel):
    ok, err = sync_messages(
        sample_slack_channel,
        start_date=date(2030, 1, 1),
        end_date=date(2020, 1, 1),
    )
    assert ok == 0 and err == 0


@pytest.mark.django_db
def test_sync_messages_fetch_raises(sample_slack_channel):
    with patch(
        "cppa_slack_tracker.sync.sync_message.fetch_messages",
        side_effect=RuntimeError("api"),
    ):
        ok, err = sync_messages(
            sample_slack_channel,
            start_date=date(2021, 1, 1),
            end_date=date(2021, 1, 2),
        )
    assert ok == 0 and err == 0


@pytest.mark.django_db
def test_sync_messages_empty_fetch(sample_slack_channel):
    with patch(
        "cppa_slack_tracker.sync.sync_message.fetch_messages",
        return_value=[],
    ):
        ok, err = sync_messages(
            sample_slack_channel,
            start_date=date(2021, 1, 1),
            end_date=date(2021, 1, 2),
        )
    assert ok == 0 and err == 0


@pytest.mark.django_db
def test_sync_messages_datetime_coercion(sample_slack_channel):
    with patch(
        "cppa_slack_tracker.sync.sync_message.fetch_messages",
        return_value=[],
    ):
        start = datetime(2021, 1, 1, tzinfo=timezone.utc)
        end = datetime(2021, 1, 2, tzinfo=timezone.utc)
        sync_messages(sample_slack_channel, start_date=start, end_date=end)


@pytest.mark.django_db
def test_sync_messages_derived_start_none_messages_without_ts(sample_slack_channel):
    with patch(
        "cppa_slack_tracker.sync.sync_message.fetch_messages",
        return_value=[{"text": "no ts"}],
    ):
        ok, err = sync_messages(
            sample_slack_channel,
            start_date=None,
            end_date=date(2025, 1, 1),
        )
    assert ok == 0 and err == 0


@pytest.mark.django_db
def test_last_message_date_accepts_plain_date_from_db(sample_slack_channel):
    import cppa_slack_tracker.sync.sync_message as sm

    qs = MagicMock()
    qs.annotate.return_value = qs
    qs.order_by.return_value = qs
    qs.values_list.return_value = qs
    qs.first.return_value = date(2024, 6, 1)
    with patch.object(sm.SlackMessage.objects, "filter", return_value=qs):
        assert sm._last_message_date(sample_slack_channel) == date(2024, 6, 1)


@pytest.mark.django_db
def test_process_workspace_jsons_invalid_json_keeps_file(
    tmp_path, sample_slack_channel, monkeypatch
):
    p = tmp_path / "broken.json"
    p.write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr(
        "cppa_slack_tracker.sync.sync_message.iter_existing_message_jsons",
        lambda **_: iter([p]),
    )
    s, e = _process_workspace_jsons(sample_slack_channel)
    assert s == 0 and e == 0
    assert p.exists()


@pytest.mark.django_db
def test_process_workspace_jsons_per_message_error_increments_errors(
    tmp_path, sample_slack_channel, monkeypatch
):
    p = tmp_path / "day.json"
    p.write_text(
        json.dumps([{"ts": "1609459200.1", "text": "x", "user": "U12345678"}]),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "cppa_slack_tracker.sync.sync_message.iter_existing_message_jsons",
        lambda **_: iter([p]),
    )
    with patch(
        "cppa_slack_tracker.sync.sync_message._process_message",
        side_effect=RuntimeError("save failed"),
    ):
        s, e = _process_workspace_jsons(sample_slack_channel)
    assert s == 0 and e == 1
    assert not p.exists()


@pytest.mark.django_db
def test_sync_messages_corrupt_raw_file_still_merges(
    sample_slack_channel,
):
    from cppa_slack_tracker.workspace import get_raw_message_json_path

    d = date(2021, 1, 1)
    raw = get_raw_message_json_path(
        sample_slack_channel.team.team_name,
        sample_slack_channel.channel_name,
        d.strftime("%Y-%m-%d"),
    )
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text("{broken-json", encoding="utf-8")
    msg = {
        "ts": "1609459200.000001",
        "user": "U12345678",
        "text": "recovered",
    }
    with patch(
        "cppa_slack_tracker.sync.sync_message.fetch_messages",
        return_value=[msg],
    ):
        ok, err = sync_messages(
            sample_slack_channel,
            start_date=d,
            end_date=d,
        )
    assert ok == 1
    assert err == 0
    data = json.loads(raw.read_text(encoding="utf-8"))
    assert any(m.get("text") == "recovered" for m in data)


@pytest.mark.django_db
def test_sync_messages_write_oserror_skips_day(sample_slack_channel):
    d = date(2021, 1, 1)
    ws = MagicMock()
    ws.parent.mkdir = MagicMock()
    ws.write_text.side_effect = OSError("no space")
    raw = MagicMock()
    raw.parent.mkdir = MagicMock()
    raw.exists.return_value = False
    msg = {"ts": "1609459200.000002", "user": "U12345678", "text": "x"}
    with (
        patch(
            "cppa_slack_tracker.sync.sync_message.get_message_json_path",
            return_value=ws,
        ),
        patch(
            "cppa_slack_tracker.sync.sync_message.get_raw_message_json_path",
            return_value=raw,
        ),
        patch(
            "cppa_slack_tracker.sync.sync_message.fetch_messages",
            return_value=[msg],
        ),
    ):
        ok, err = sync_messages(
            sample_slack_channel,
            start_date=d,
            end_date=d,
        )
    assert ok == 0
    assert err == 0


@pytest.mark.django_db
def test_sync_messages_unlink_failure_after_process(sample_slack_channel):
    d = date(2021, 1, 1)
    ws = MagicMock()
    ws.parent.mkdir = MagicMock()
    ws.write_text = MagicMock()
    ws.unlink.side_effect = RuntimeError("unlink blocked")
    raw = MagicMock()
    raw.parent.mkdir = MagicMock()
    raw.exists.return_value = False
    raw.write_text = MagicMock()
    msg = {"ts": "1609459200.000003", "user": "U12345678", "text": "y"}
    with (
        patch(
            "cppa_slack_tracker.sync.sync_message.get_message_json_path",
            return_value=ws,
        ),
        patch(
            "cppa_slack_tracker.sync.sync_message.get_raw_message_json_path",
            return_value=raw,
        ),
        patch(
            "cppa_slack_tracker.sync.sync_message.fetch_messages",
            return_value=[msg],
        ),
        patch(
            "cppa_slack_tracker.sync.sync_message._process_message",
            return_value=True,
        ),
    ):
        ok, err = sync_messages(
            sample_slack_channel,
            start_date=d,
            end_date=d,
        )
    assert ok == 1
    assert err == 0


@pytest.mark.django_db
def test_sync_channels_single_channel_process_raises(
    sample_slack_team, sample_slack_channel_data
):
    mock_client = MagicMock()
    mock_client.conversations_info.return_value = {
        "ok": True,
        "channel": sample_slack_channel_data,
    }
    with (
        patch(
            "core.operations.slack_ops.tokens.get_slack_client",
            return_value=mock_client,
        ),
        patch(
            "cppa_slack_tracker.sync.sync_channel.get_or_create_slack_channel",
            side_effect=RuntimeError("db"),
        ),
    ):
        ok, err = sync_channels(
            sample_slack_team,
            channel_id=sample_slack_channel_data["id"],
            team_id=sample_slack_team.team_id,
        )
    assert ok == 0 and err == 1


@pytest.mark.django_db
def test_sync_channels_list_item_process_raises(
    sample_slack_team, sample_slack_channel_data
):
    with (
        patch(
            "cppa_slack_tracker.sync.sync_channel.fetch_channel_list",
            return_value=[sample_slack_channel_data],
        ),
        patch(
            "cppa_slack_tracker.sync.sync_channel.get_or_create_slack_channel",
            side_effect=RuntimeError("sync one channel"),
        ),
    ):
        ok, err = sync_channels(sample_slack_team, team_id=sample_slack_team.team_id)
    assert ok == 0 and err == 1


@pytest.mark.django_db
def test_sync_users_process_user_raises():
    with (
        patch(
            "cppa_slack_tracker.sync.sync_user.fetch_user_list",
            return_value=[{"id": "Ubad", "name": "x"}],
        ),
        patch(
            "cppa_slack_tracker.sync.sync_user.get_or_create_slack_user",
            side_effect=RuntimeError("user sync"),
        ),
    ):
        ok, err = sync_users("slug", team_id="T1")
    assert ok == 0 and err == 1
