"""Tests for boost_mailing_list_tracker.fetcher.

Covers edge cases and boundaries: empty inputs, date filtering,
format_email with missing/None/invalid data, _get_start_date_from_db format.
"""

import json
import logging
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests
from requests.exceptions import HTTPError

from boost_mailing_list_tracker import fetcher


# --- _filter_by_date ---


def test_filter_by_date_empty_results():
    """_filter_by_date with empty results returns empty list and should_stop=False."""
    filtered, stop = fetcher._filter_by_date([], "2024-01-01", "2024-12-31")
    assert filtered == []
    assert stop is False


def test_filter_by_date_empty_start_and_end():
    """_filter_by_date with empty start_date and end_date includes all items."""
    results = [
        {"date": "2024-06-01T12:00:00Z"},
        {"date": "2024-06-02T12:00:00Z"},
    ]
    filtered, stop = fetcher._filter_by_date(results, "", "")
    assert len(filtered) == 2
    assert stop is False


def test_filter_by_date_stop_when_before_start():
    """_filter_by_date sets should_stop when item date is before start_date."""
    results = [
        {"date": "2024-06-15T12:00:00Z"},
        {"date": "2024-06-01T12:00:00Z"},  # before start -> stop
    ]
    filtered, stop = fetcher._filter_by_date(
        results,
        start_date="2024-06-10T00:00:00Z",
        end_date="",
    )
    assert len(filtered) == 1
    assert filtered[0]["date"] == "2024-06-15T12:00:00Z"
    assert stop is True


def test_filter_by_date_excludes_after_end():
    """_filter_by_date excludes items with date after end_date."""
    results = [
        {"date": "2024-06-15T12:00:00Z"},
        {"date": "2024-06-20T12:00:00Z"},  # after end
        {"date": "2024-06-10T12:00:00Z"},
    ]
    end_date_str = "2024-06-15T23:59:59Z"
    filtered, stop = fetcher._filter_by_date(
        results,
        start_date="",
        end_date=end_date_str,
    )
    end_dt = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
    assert len(filtered) == 2
    for item in filtered:
        item_dt = datetime.fromisoformat(item["date"].replace("Z", "+00:00"))
        assert item_dt <= end_dt
    assert stop is False


def test_filter_by_date_boundary_equal_to_start():
    """_filter_by_date includes item when date equals start_date."""
    results = [{"date": "2024-06-10T00:00:00Z"}]
    filtered, stop = fetcher._filter_by_date(
        results,
        start_date="2024-06-10T00:00:00Z",
        end_date="",
    )
    assert len(filtered) == 1
    assert stop is False


def test_filter_by_date_missing_date_in_item():
    """_filter_by_date handles items with missing or None date (no crash)."""
    results = [
        {"date": "2024-06-01T12:00:00Z"},
        {},  # no date
        {"date": None},
        {"subject": "no date"},
    ]
    filtered, _ = fetcher._filter_by_date(
        results,
        start_date="2024-05-01T00:00:00Z",
        end_date="2024-12-31T23:59:59Z",
    )
    # First item included; others have no date so skipped
    assert len(filtered) >= 1
    assert filtered[0]["date"] == "2024-06-01T12:00:00Z"


def test_filter_by_date_all_before_start():
    """_filter_by_date returns empty and stop=True when first item is before start."""
    results = [{"date": "2024-01-01T00:00:00Z"}]
    filtered, stop = fetcher._filter_by_date(
        results,
        start_date="2024-06-01T00:00:00Z",
        end_date="",
    )
    assert filtered == []
    assert stop is True


# --- format_email ---


def test_format_email_minimal_item():
    """format_email handles minimal item with only required keys."""
    item = {}
    source_url = (
        "https://lists.boost.org/archives/api/list/boost@lists.boost.org/emails/"
    )
    out = fetcher.format_email(item, source_url)
    assert out["msg_id"] == ""
    assert out["parent_id"] == ""
    assert out["thread_id"] == ""
    assert out["subject"] == ""
    assert out["content"] == ""
    assert out["list_name"] == "boost@lists.boost.org"
    assert out["sent_at"] is None
    assert "sender_address" in out
    assert "sender_name" in out


def test_format_email_full_item():
    """format_email maps all fields from a full API-like item."""
    item = {
        "message_id_hash": "<msg-123@lists.boost.org>",
        "parent": "https://lists.boost.org/archives/api/thread/456/",
        "thread": "https://lists.boost.org/archives/api/thread/789/",
        "subject": "Test subject",
        "content": "Body",
        "date": "2024-06-15T12:00:00Z",
        "sender": {"address": "user (a) example.com", "other": "ignored"},
        "sender_name": "Test User",
    }
    source_url = (
        "https://lists.boost.org/archives/api/list/boost-users@lists.boost.org/emails/"
    )
    out = fetcher.format_email(item, source_url)
    assert out["msg_id"] == "<msg-123@lists.boost.org>"
    assert out["parent_id"] == "456"
    assert out["thread_id"] == "789"
    assert out["subject"] == "Test subject"
    assert out["content"] == "Body"
    assert out["list_name"] == "boost-users@lists.boost.org"
    assert out["sent_at"] == "2024-06-15T12:00:00Z"
    assert out["sender_address"] == "user@example.com"
    assert out["sender_name"] == "Test User"


def test_format_email_sender_none():
    """format_email handles missing or None sender."""
    item = {"message_id_hash": "<x@y>", "sender": None}
    source_url = (
        "https://lists.boost.org/archives/api/list/boost@lists.boost.org/emails/"
    )
    out = fetcher.format_email(item, source_url)
    assert out["sender_address"] == ""
    assert out["sender_name"] == ""


def test_format_email_sender_missing_address():
    """format_email handles sender dict without address key."""
    item = {"message_id_hash": "<x@y>", "sender": {}}
    source_url = (
        "https://lists.boost.org/archives/api/list/boost@lists.boost.org/emails/"
    )
    out = fetcher.format_email(item, source_url)
    assert out["sender_address"] == ""


def test_format_email_parent_thread_with_trailing_slash():
    """format_email extracts id from parent/thread URLs (segment before final empty)."""
    item = {
        "message_id_hash": "<id>",
        "parent": "https://example.com/thread/123/",
        "thread": "https://example.com/thread/456/",
    }
    source_url = (
        "https://lists.boost.org/archives/api/list/boost@lists.boost.org/emails/"
    )
    out = fetcher.format_email(item, source_url)
    assert out["parent_id"] == "123"
    assert out["thread_id"] == "456"


def test_format_email_parent_thread_empty_string():
    """format_email handles empty parent/thread (split gives empty or single segment)."""
    item = {"message_id_hash": "<id>", "parent": "", "thread": ""}
    source_url = (
        "https://lists.boost.org/archives/api/list/boost@lists.boost.org/emails/"
    )
    out = fetcher.format_email(item, source_url)
    assert out["parent_id"] == ""
    assert out["thread_id"] == ""


def test_format_email_list_name_from_url():
    """format_email derives list_name from source_url path (-3 segment)."""
    source_url = "https://lists.boost.org/archives/api/list/boost-announce@lists.boost.org/emails/"
    out = fetcher.format_email({"message_id_hash": "x"}, source_url)
    assert out["list_name"] == "boost-announce@lists.boost.org"


# --- _get_start_date_from_db ---


@pytest.mark.django_db
def test_get_start_date_from_db_empty_returns_empty_string():
    """_get_start_date_from_db returns empty string when no messages in DB."""
    result = fetcher._get_start_date_from_db()
    assert result == ""


@pytest.mark.django_db
def test_get_start_date_from_db_returns_iso_utc_format(
    mailing_list_profile,
    default_list_name,
):
    """_get_start_date_from_db returns ISO 8601 UTC format like 2025-11-13T05:25:55Z."""
    from boost_mailing_list_tracker import services

    dt = datetime(2025, 11, 13, 5, 25, 55, tzinfo=timezone.utc)
    services.get_or_create_mailing_list_message(
        mailing_list_profile.pk,
        msg_id="<start-date-test@example.com>",
        sent_at=dt,
        list_name=default_list_name,
    )
    result = fetcher._get_start_date_from_db()
    assert result == "2025-11-13T05:25:55Z"


@pytest.mark.django_db
def test_get_start_date_from_db_uses_latest_sent_at(
    mailing_list_profile,
    default_list_name,
):
    """_get_start_date_from_db returns the latest sent_at among all messages."""
    from boost_mailing_list_tracker import services

    services.get_or_create_mailing_list_message(
        mailing_list_profile.pk,
        msg_id="<older@example.com>",
        sent_at=datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
        list_name=default_list_name,
    )
    services.get_or_create_mailing_list_message(
        mailing_list_profile.pk,
        msg_id="<newer@example.com>",
        sent_at=datetime(2025, 6, 15, 14, 30, 0, tzinfo=timezone.utc),
        list_name=default_list_name,
    )
    result = fetcher._get_start_date_from_db()
    assert result == "2025-06-15T14:30:00Z"


@pytest.mark.django_db
def test_get_start_date_from_db_utc_aware_sent_at_iso_format(
    mailing_list_profile,
    default_list_name,
):
    """_get_start_date_from_db returns ISO UTC for timezone-aware sent_at (USE_TZ-safe)."""
    from boost_mailing_list_tracker import services

    dt_utc = datetime(2025, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
    services.get_or_create_mailing_list_message(
        mailing_list_profile.pk,
        msg_id="<utc@example.com>",
        sent_at=dt_utc,
        list_name=default_list_name,
    )
    result = fetcher._get_start_date_from_db()
    assert result == "2025-03-10T12:00:00Z"


def test_get_start_date_from_db_naive_aggregate_value_gets_z_suffix():
    """If Max(sent_at) is naive, strftime still emits ...Z (defensive path)."""
    with patch(
        "boost_mailing_list_tracker.models.MailingListMessage.objects.aggregate",
        return_value={"sent_at__max": datetime(2025, 3, 10, 12, 0, 0)},
    ):
        result = fetcher._get_start_date_from_db()
    assert result == "2025-03-10T12:00:00Z"


# --- fetch_email_list (integration with mock) ---


def test_fetch_email_list_returns_none_on_fetch_failure():
    """fetch_email_list returns None when _fetch_page returns None."""
    with patch.object(fetcher, "_fetch_page", return_value=None):
        result = fetcher.fetch_email_list(
            "https://lists.boost.org/archives/api/list/boost@lists.boost.org/emails/",
            start_date="",
            end_date="",
        )
    assert result is None


def test_fetch_email_list_returns_none_when_no_results():
    """fetch_email_list returns None when API returns empty results."""
    with patch.object(
        fetcher, "_fetch_page", return_value={"results": [], "next": None}
    ):
        result = fetcher.fetch_email_list(
            "https://lists.boost.org/archives/api/list/boost@lists.boost.org/emails/",
        )
    assert result is None


def test_fetch_email_list_returns_filtered_results():
    """fetch_email_list returns list from results and respects date filter."""
    with patch.object(
        fetcher,
        "_fetch_page",
        return_value={
            "results": [
                {"date": "2024-06-15T12:00:00Z", "url": "https://example.com/1"}
            ],
            "next": None,
        },
    ):
        result = fetcher.fetch_email_list(
            "https://lists.boost.org/archives/api/list/boost@lists.boost.org/emails/",
            start_date="",
            end_date="2024-12-31T23:59:59Z",
        )
    assert result is not None
    assert len(result) == 1
    assert result[0]["date"] == "2024-06-15T12:00:00Z"


# --- _parse_datetime / _parse_end_bound ---


def test_parse_datetime_empty_and_invalid():
    assert fetcher._parse_datetime("") is None
    assert fetcher._parse_datetime("   ") is None
    assert fetcher._parse_datetime("not-a-date") is None


def test_parse_datetime_z_suffix_and_naive_gets_utc():
    dt = fetcher._parse_datetime("2024-06-15T12:00:00Z")
    assert dt is not None
    assert dt.tzinfo == timezone.utc
    naive = fetcher._parse_datetime("2024-06-15T12:00:00")
    assert naive is not None
    assert naive.tzinfo == timezone.utc


def test_parse_end_bound_date_only_extends_to_end_of_day():
    end_dt = fetcher._parse_end_bound("2024-06-15")
    assert end_dt is not None
    assert end_dt.hour == 23 and end_dt.minute == 59 and end_dt.second == 59


def test_parse_end_bound_datetime_unchanged():
    end_dt = fetcher._parse_end_bound("2024-06-15T12:00:00Z")
    assert end_dt is not None
    assert end_dt.hour == 12


# --- _filter_by_date invalid date ---


def test_filter_by_date_skips_invalid_date_string():
    results = [
        {"date": "not-parseable", "message_id_hash": "x"},
        {"date": "2024-06-15T12:00:00Z"},
    ]
    filtered, stop = fetcher._filter_by_date(results, "", "")
    assert len(filtered) == 1
    assert filtered[0]["date"] == "2024-06-15T12:00:00Z"
    assert stop is False


# --- _path_tail ---


def test_path_tail_empty_and_url():
    assert fetcher._path_tail("") == ""
    assert fetcher._path_tail(None) == ""
    assert fetcher._path_tail("https://ex/a/b/") == "b"
    assert fetcher._path_tail("plain-id") == "plain-id"


# --- _fetch_page ---


def test_fetch_page_appends_limit_offset_when_no_query():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"results": []}
    mock_resp.raise_for_status = MagicMock()
    with patch.object(fetcher.requests, "get", return_value=mock_resp) as get:
        fetcher._fetch_page("https://lists.boost.org/api/list/x/emails/", page=2)
    url = get.call_args[0][0]
    assert "limit=" in url and "offset=100" in url


def test_fetch_page_preserves_url_when_query_present():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {}
    mock_resp.raise_for_status = MagicMock()
    with patch.object(fetcher.requests, "get", return_value=mock_resp) as get:
        fetcher._fetch_page("https://next?page=cursor", page=3)
    get.assert_called_once_with(
        "https://next?page=cursor", timeout=fetcher.REQUEST_TIMEOUT
    )


def test_fetch_page_429_retry_after_header_then_success():
    rate_limited = MagicMock(status_code=429)
    rate_limited.headers = {"Retry-After": "0"}
    ok = MagicMock(status_code=200)
    ok.json.return_value = {"ok": True}
    ok.raise_for_status = MagicMock()
    with patch.object(fetcher.requests, "get", side_effect=[rate_limited, ok]):
        with patch.object(fetcher.time, "sleep"):
            out = fetcher._fetch_page("https://example.com/a/", page=1)
    assert out == {"ok": True}


def test_fetch_page_429_retry_after_json_body():
    rate_limited = MagicMock(status_code=429)
    rate_limited.headers = {}
    rate_limited.json.return_value = {"retry_after": 0}
    ok = MagicMock(status_code=200)
    ok.json.return_value = {"x": 1}
    ok.raise_for_status = MagicMock()
    with patch.object(fetcher.requests, "get", side_effect=[rate_limited, ok]):
        with patch.object(fetcher.time, "sleep"):
            out = fetcher._fetch_page("https://example.com/a/", page=1)
    assert out == {"x": 1}


def test_fetch_page_429_exhausted_returns_none():
    rate_limited = MagicMock(status_code=429)
    rate_limited.headers = {}
    rate_limited.json.return_value = {}
    with patch.object(fetcher.requests, "get", return_value=rate_limited):
        with patch.object(fetcher.time, "sleep"):
            out = fetcher._fetch_page("https://example.com/a/", page=1)
    assert out is None


def test_fetch_page_http_error_non_429_returns_none():
    resp404 = MagicMock()
    resp404.status_code = 404
    err = HTTPError(response=resp404)
    resp404.raise_for_status.side_effect = err
    with patch.object(fetcher.requests, "get", return_value=resp404):
        assert fetcher._fetch_page("https://example.com/", page=1) is None


def test_fetch_page_request_exception_returns_none():
    with patch.object(
        fetcher.requests,
        "get",
        side_effect=requests.exceptions.ConnectionError("refused"),
    ):
        assert fetcher._fetch_page("https://example.com/", page=1) is None


def test_fetch_page_json_decode_error_returns_none():
    mock_resp = MagicMock(status_code=200)
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.side_effect = json.JSONDecodeError("msg", "doc", 0)
    with patch.object(fetcher.requests, "get", return_value=mock_resp):
        assert fetcher._fetch_page("https://example.com/", page=1) is None


# --- fetch_email_list pagination / empty ---


def test_fetch_email_list_two_pages_merges_results():
    page1 = {
        "results": [{"date": "2024-06-15T12:00:00Z", "id": 1}],
        "next": "https://api/next?cursor=2",
    }
    page2 = {
        "results": [{"date": "2024-06-14T12:00:00Z", "id": 2}],
        "next": None,
    }
    with patch.object(fetcher, "_fetch_page", side_effect=[page1, page2]):
        result = fetcher.fetch_email_list(
            "https://lists.boost.org/archives/api/list/boost@lists.boost.org/emails/",
            "",
            "",
        )
    assert result is not None
    assert len(result) == 2


def test_fetch_email_list_returns_none_when_all_filtered_out():
    """Empty aggregate list yields None (not only when _fetch_page fails)."""
    with patch.object(
        fetcher,
        "_fetch_page",
        return_value={
            "results": [{"date": "2020-01-01T00:00:00Z"}],
            "next": None,
        },
    ):
        result = fetcher.fetch_email_list(
            "https://lists.boost.org/archives/api/list/boost@lists.boost.org/emails/",
            start_date="2024-01-01T00:00:00Z",
            end_date="",
        )
    assert result is None


def test_fetch_email_list_page_increment_on_next():
    with patch.object(fetcher, "_fetch_page") as fp:
        fp.side_effect = [
            {"results": [], "next": "http://x?y=1"},
            {"results": [{"date": "2024-06-01T00:00:00Z"}], "next": None},
        ]
        fetcher.fetch_email_list(
            "https://lists.boost.org/archives/api/list/boost@lists.boost.org/emails/",
            "",
            "",
        )
    assert fp.call_args_list[1][0][1] == 2


# --- fetch_all_emails ---


def test_fetch_all_emails_formats_and_saves_raw(tmp_path):
    api_url = "https://lists.boost.org/archives/api/list/boost@lists.boost.org/emails/"
    content = {
        "message_id_hash": "<raw-test@lists.boost.org>",
        "subject": "Subj",
        "content": "Body",
        "date": "2024-06-01T00:00:00Z",
        "sender": {"address": "u (a) example.com"},
    }

    with patch(
        "boost_mailing_list_tracker.workspace.get_workspace_path",
        side_effect=lambda slug: tmp_path / slug,
    ):
        with patch.object(
            fetcher,
            "fetch_email_list",
            return_value=[
                {
                    "url": "https://lists.boost.org/archives/api/email/foo/",
                    "date": "2024-06-01T00:00:00Z",
                }
            ],
        ):
            with patch.object(fetcher, "_fetch_page", return_value=content):
                out = fetcher.fetch_all_emails(
                    start_date="2024-01-01",
                    end_date="",
                    list_urls=[api_url],
                )
    assert len(out) == 1
    assert out[0]["msg_id"] == "<raw-test@lists.boost.org>"
    raw_dir = tmp_path / "raw" / "boost_mailing_list_tracker" / "boost@lists.boost.org"
    assert raw_dir.is_dir()
    json_files = list(raw_dir.glob("*.json"))
    assert len(json_files) == 1


def test_fetch_all_emails_skips_row_without_url():
    api_url = "https://lists.boost.org/archives/api/list/boost@lists.boost.org/emails/"
    with patch.object(
        fetcher,
        "fetch_email_list",
        return_value=[{"date": "2024-06-01T00:00:00Z"}],
    ):
        out = fetcher.fetch_all_emails(
            start_date="2024-01-01",
            list_urls=[api_url],
        )
    assert out == []


def test_fetch_all_emails_skips_when_content_fetch_returns_none():
    api_url = "https://lists.boost.org/archives/api/list/boost@lists.boost.org/emails/"
    with patch.object(
        fetcher,
        "fetch_email_list",
        return_value=[
            {
                "url": "https://lists.boost.org/archives/api/email/x/",
                "date": "2024-06-01",
            }
        ],
    ):
        with patch.object(fetcher, "_fetch_page", return_value=None):
            out = fetcher.fetch_all_emails(
                start_date="2024-01-01",
                list_urls=[api_url],
            )
    assert out == []


def test_fetch_all_emails_skips_when_msg_id_empty_after_format():
    api_url = "https://lists.boost.org/archives/api/list/boost@lists.boost.org/emails/"
    with patch.object(
        fetcher,
        "fetch_email_list",
        return_value=[
            {
                "url": "https://lists.boost.org/archives/api/email/x/",
                "date": "2024-06-01",
            }
        ],
    ):
        with patch.object(
            fetcher,
            "_fetch_page",
            return_value={
                "message_id_hash": "",
                "subject": "",
                "content": "",
                "date": None,
            },
        ):
            out = fetcher.fetch_all_emails(
                start_date="2024-01-01",
                list_urls=[api_url],
            )
    assert out == []


@pytest.mark.django_db
def test_fetch_all_emails_inserts_start_date_from_database_when_blank(
    mailing_list_profile,
    default_list_name,
    caplog,
):
    """When start_date is omitted, fetch_email_list receives latest sent_at from DB."""
    from boost_mailing_list_tracker import services

    dt = datetime(2024, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
    services.get_or_create_mailing_list_message(
        mailing_list_profile.pk,
        msg_id="<db-start@example.com>",
        sent_at=dt,
        list_name=default_list_name,
    )
    api_url = "https://lists.boost.org/archives/api/list/boost@lists.boost.org/emails/"
    with patch.object(fetcher, "fetch_email_list", return_value=[]) as fel:
        with caplog.at_level(logging.INFO):
            fetcher.fetch_all_emails(start_date="", end_date="", list_urls=[api_url])
    fel.assert_called_once()
    assert fel.call_args[0][1] == "2024-03-01T12:00:00Z"
    assert "Using start_date from DB" in caplog.text


def test_fetch_all_emails_logs_warning_when_no_index_rows(caplog):
    api_url = "https://lists.boost.org/archives/api/list/boost@lists.boost.org/emails/"
    with patch.object(fetcher, "fetch_email_list", return_value=[]):
        with caplog.at_level(logging.WARNING):
            fetcher.fetch_all_emails(start_date="2024-01-01", list_urls=[api_url])
    assert "No email index data" in caplog.text
