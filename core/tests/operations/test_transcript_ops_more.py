"""Tests for core.operations.md_ops.transcript."""

from unittest.mock import patch

import pytest

from core.operations.md_ops.transcript import (
    generate_transcript_from_json,
    parse_datetime_range,
    parse_html_summary,
    replace_channel_ids_with_names,
    replace_user_ids_with_usernames,
    write_huddle_transcript_md,
)


def test_parse_datetime_range_preserves_on_bad_match():
    assert parse_datetime_range("no times here") == "no times here"


def test_parse_datetime_range_with_pst_suffix():
    out = parse_datetime_range(
        "10:00:00 AM - 11:00:00 AM PST",
        date_str="01/15/24",
    )
    assert "PST" in out


def test_parse_html_summary_extracts_channel_and_attendees():
    html = """
    <html>#C01234567 Huddle notes: 1/15/24
    <b>10:00:00 AM - 11:00:00 AM PST</b>
    <h2>Attendees</h2><p>@U111 @U222</p></html>
    """
    data = parse_html_summary(html)
    assert data["channel_id"] == "C01234567"
    assert "U111" in data["attendee_ids"]


def test_replace_user_ids():
    md = "Hello @U1 there"
    out = replace_user_ids_with_usernames(md, {"U1": {"display_name": "Alice"}})
    assert "Alice" in out


def test_replace_channel_ids():
    md = "Join #C99 please"
    assert "#general" in replace_channel_ids_with_names(md, "C99", "general")


def test_generate_transcript_from_json_list_blocks():
    payload = {
        "file": {
            "huddle_transcription": {
                "blocks": [
                    {
                        "elements": [
                            {
                                "type": "rich_text_section",
                                "elements": [
                                    {"type": "user", "user_id": "U9"},
                                    {"type": "text", "text": "[10:15]: "},
                                    {"type": "text", "text": "hello"},
                                ],
                            }
                        ]
                    }
                ]
            }
        }
    }
    rows = generate_transcript_from_json(payload)
    assert rows and rows[0]["user_id"] == "U9"


def test_generate_transcript_dict_blocks_elements():
    payload = {
        "file": {
            "huddle_transcription": {
                "blocks": {"elements": []},
            }
        }
    }
    assert generate_transcript_from_json(payload) == []


@pytest.mark.django_db
def test_write_huddle_transcript_md_writes_file(tmp_path):
    html = """
    #C01234567 Huddle notes: 1/15/24
    <b>10:00:00 AM - 11:00:00 AM PST</b>
    <h2>Attendees</h2><p>@U1</p>
    """
    result_json = {
        "file": {
            "huddle_transcription": {
                "blocks": [
                    {
                        "elements": [
                            {
                                "type": "rich_text_section",
                                "elements": [
                                    {"type": "user", "user_id": "U1"},
                                    {"type": "text", "text": "hi"},
                                ],
                            }
                        ]
                    }
                ]
            }
        }
    }
    path = write_huddle_transcript_md(
        tmp_path,
        html_content=html,
        result_json=result_json,
        channel_name="team-chat",
        user_info_map={"U1": {"display_name": "Sam"}},
        summary_markdown="Summary line",
    )
    assert path is not None
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "team-chat" in text
    assert "Summary line" in text


def test_write_huddle_transcript_md_write_error(tmp_path):
    with patch(
        "core.operations.md_ops.transcript.write_markdown",
        side_effect=OSError("fail"),
    ):
        out = write_huddle_transcript_md(
            tmp_path,
            html_content="<html>#C1 Huddle notes: 1/1/24<b>t</b></html>",
            result_json={"file": {"huddle_transcription": {"blocks": []}}},
            channel_name="c",
            user_info_map={},
            summary_markdown="",
        )
    assert out is None


def test_parse_datetime_range_with_utc_suffix():
    out = parse_datetime_range(
        "10:00:00 AM - 11:00:00 AM UTC",
        date_str="01/15/2024",
    )
    assert "PST" in out


def test_parse_datetime_range_end_before_start_crosses_midnight():
    out = parse_datetime_range(
        "11:00:00 PM - 01:00:00 AM PST",
        date_str="06/01/24",
    )
    assert "PST" in out and "_" in out


def test_parse_datetime_range_invalid_date_str_falls_back():
    out = parse_datetime_range(
        "10:00:00 AM - 11:00:00 AM PST",
        date_str="not-a-date",
    )
    assert "PST" in out


def test_replace_channel_ids_noop_without_channel_id():
    assert replace_channel_ids_with_names("#C1 here", None, "general") == "#C1 here"


def test_generate_transcript_skips_non_dict_block():
    payload = {
        "file": {
            "huddle_transcription": {
                "blocks": ["bad", {"elements": []}],
            }
        }
    }
    assert generate_transcript_from_json(payload) == []


def test_generate_transcript_non_dict_file_data_returns_empty():
    assert generate_transcript_from_json({"file": object()}) == []


def test_replace_user_ids_prefers_real_name_when_no_display():
    md = "Hi @U55"
    out = replace_user_ids_with_usernames(
        md,
        {"U55": {"real_name": "Real N", "name": "u55"}},
    )
    assert "Real N" in out
