"""Tests for cppa_youtube_script_tracker.fetcher."""

import builtins
import sys
import types
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from django.test.utils import override_settings

from cppa_youtube_script_tracker import fetcher as fetcher_mod
from cppa_youtube_script_tracker.fetcher import QuotaExceededError, fetch_videos


@contextmanager
def _stub_googleapiclient_build(youtube_client):
    """Inject a minimal googleapiclient.discovery package (may be absent in dev env)."""
    discovery = types.ModuleType("googleapiclient.discovery")
    discovery.build = MagicMock(return_value=youtube_client)
    google_pkg = types.ModuleType("googleapiclient")
    google_pkg.discovery = discovery
    old_g = sys.modules.get("googleapiclient")
    old_d = sys.modules.get("googleapiclient.discovery")
    sys.modules["googleapiclient"] = google_pkg
    sys.modules["googleapiclient.discovery"] = discovery
    try:
        yield discovery.build
    finally:
        if old_g is not None:
            sys.modules["googleapiclient"] = old_g
        else:
            sys.modules.pop("googleapiclient", None)
        if old_d is not None:
            sys.modules["googleapiclient.discovery"] = old_d
        else:
            sys.modules.pop("googleapiclient.discovery", None)


def test_parse_duration_iso():
    assert fetcher_mod._parse_duration_iso("") == 0
    assert fetcher_mod._parse_duration_iso("PT") == 0
    assert fetcher_mod._parse_duration_iso("PT1H2M3S") == 3723
    assert fetcher_mod._parse_duration_iso("bad") == 0


def test_get_api_key_missing_and_present():
    with override_settings(YOUTUBE_API_KEY=""):
        with pytest.raises(ValueError, match="YOUTUBE_API_KEY"):
            fetcher_mod._get_api_key()
    with override_settings(YOUTUBE_API_KEY=" abc "):
        assert fetcher_mod._get_api_key() == "abc"


def test_is_quota_exceeded_error():
    assert fetcher_mod._is_quota_exceeded_error(RuntimeError("quotaExceeded")) is True
    assert fetcher_mod._is_quota_exceeded_error(RuntimeError("youtube.quota")) is True
    assert fetcher_mod._is_quota_exceeded_error(RuntimeError("other")) is False


def test_get_max_query_pairs():
    with override_settings(YOUTUBE_MAX_QUERY_PAIRS="not-int"):
        assert (
            fetcher_mod._get_max_query_pairs() == fetcher_mod._DEFAULT_MAX_QUERY_PAIRS
        )
    with override_settings(YOUTUBE_MAX_QUERY_PAIRS=3):
        assert fetcher_mod._get_max_query_pairs() == 3
    with override_settings(YOUTUBE_MAX_QUERY_PAIRS=0):
        assert fetcher_mod._get_max_query_pairs() == 1


def test_format_video_data_and_to_rfc3339():
    vd = {
        "id": "abc",
        "snippet": {
            "title": "T",
            "description": "D",
            "channelId": "cid",
            "channelTitle": "CT",
            "publishedAt": "2020-01-01T00:00:00Z",
            "tags": ["x"],
        },
        "statistics": {"viewCount": "10", "likeCount": "2", "commentCount": "1"},
        "contentDetails": {"duration": "PT1M"},
    }
    out = fetcher_mod._format_video_data(vd, search_term="q")
    assert out["video_id"] == "abc"
    assert out["duration_seconds"] == 60
    assert out["view_count"] == 10
    assert out["search_term"] == "q"

    naive = datetime(2024, 6, 1, 12, 0, 0)
    assert fetcher_mod._to_rfc3339(naive).endswith("Z")

    aware = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert "2024-06-01" in fetcher_mod._to_rfc3339(aware)


def test_build_queries_known_channel_and_unknown():
    pairs = fetcher_mod._build_queries("CppCon")
    assert pairs
    assert all(pid == fetcher_mod.C_PLUS_PLUS_CHANNELS["CppCon"] for _, pid in pairs)

    pairs_unknown = fetcher_mod._build_queries("Unknown Channel")
    texts = [t for t, _ in pairs_unknown]
    assert "Unknown Channel" in texts


@override_settings(YOUTUBE_API_KEY="k")
def test_fetch_videos_happy_path():
    youtube = MagicMock()
    search_exec = MagicMock(
        return_value={
            "items": [
                {"id": {"kind": "youtube#video", "videoId": "v1"}},
            ],
            "nextPageToken": None,
        }
    )
    youtube.search.return_value.list.return_value.execute = search_exec

    detail_item = {
        "id": "v1",
        "snippet": {"title": "Hi"},
        "statistics": {},
        "contentDetails": {"duration": "PT10S"},
    }
    vid_exec = MagicMock(return_value={"items": [detail_item]})
    youtube.videos.return_value.list.return_value.execute = vid_exec

    with _stub_googleapiclient_build(youtube):
        with patch.object(fetcher_mod.time, "sleep"):
            out = fetch_videos(
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 12, 31, tzinfo=timezone.utc),
                channel_title="CppCon",
                skip_video_ids=set(),
                min_duration_seconds=0,
            )
    assert len(out) == 1
    assert out[0]["video_id"] == "v1"


def test_fetch_search_page_quota_raises():
    youtube = MagicMock()

    def search_execute():
        raise RuntimeError("quotaExceeded")

    youtube.search.return_value.list.return_value.execute = search_execute

    with pytest.raises(QuotaExceededError):
        fetcher_mod._fetch_search_page(youtube, "q", None, "a", "b", None)


def test_fetch_search_page_generic_error_returns_none():
    youtube = MagicMock()
    youtube.search.return_value.list.return_value.execute.side_effect = RuntimeError(
        "generic"
    )
    assert fetcher_mod._fetch_search_page(youtube, "q", None, "a", "b", None) is None


def test_fetch_video_details_quota_raises():
    youtube = MagicMock()
    youtube.videos.return_value.list.return_value.execute.side_effect = RuntimeError(
        "quotaExceeded"
    )
    with pytest.raises(QuotaExceededError):
        fetcher_mod._fetch_video_details(youtube, ["x"])


def test_fetch_video_details_generic_error_returns_empty():
    youtube = MagicMock()
    youtube.videos.return_value.list.return_value.execute.side_effect = RuntimeError(
        "generic"
    )
    assert fetcher_mod._fetch_video_details(youtube, ["x"]) == []


@override_settings(YOUTUBE_API_KEY="k")
def test_fetch_videos_quota_exhausted_returns_partial():
    youtube = MagicMock()
    youtube.search.return_value.list.return_value.execute.side_effect = RuntimeError(
        "quotaExceeded"
    )
    with _stub_googleapiclient_build(youtube):
        with patch.object(fetcher_mod.time, "sleep"):
            out = fetch_videos(
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 2, 1, tzinfo=timezone.utc),
                channel_title="CppCon",
            )
    assert out == []


@override_settings(YOUTUBE_API_KEY="k")
def test_fetch_videos_truncates_query_pairs(caplog):
    import logging

    youtube = MagicMock()
    youtube.search.return_value.list.return_value.execute = MagicMock(
        return_value={"items": [], "nextPageToken": None}
    )
    caplog.set_level(logging.WARNING)
    with _stub_googleapiclient_build(youtube):
        with patch.object(fetcher_mod.time, "sleep"):
            with override_settings(YOUTUBE_MAX_QUERY_PAIRS=1):
                fetch_videos(
                    datetime(2024, 1, 1, tzinfo=timezone.utc),
                    datetime(2024, 2, 1, tzinfo=timezone.utc),
                    channel_title=None,
                )
    assert any("truncated" in r.message for r in caplog.records)


@override_settings(YOUTUBE_API_KEY="k")
def test_process_one_channel_query_skips_short_duration():
    youtube = MagicMock()
    search_exec = MagicMock(
        return_value={
            "items": [{"id": {"kind": "youtube#video", "videoId": "s1"}}],
            "nextPageToken": None,
        }
    )
    youtube.search.return_value.list.return_value.execute = search_exec
    youtube.videos.return_value.list.return_value.execute = MagicMock(
        return_value={
            "items": [
                {
                    "id": "s1",
                    "snippet": {},
                    "statistics": {},
                    "contentDetails": {"duration": "PT5S"},
                }
            ]
        }
    )
    seen: set[str] = set()
    with patch.object(fetcher_mod.time, "sleep"):
        out = fetcher_mod._process_one_channel_query(
            youtube,
            "q",
            None,
            "a",
            "b",
            seen,
            min_duration_seconds=9999,
        )
    assert out == []


@override_settings(YOUTUBE_API_KEY="k")
def test_fetch_videos_import_error():
    real_import = builtins.__import__

    def fake_import(name, globals_=None, locals_=None, fromlist=(), level=0):
        if name == "googleapiclient.discovery":
            raise ImportError("simulated missing google client")
        return real_import(name, globals_, locals_, fromlist, level)

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(ImportError, match="google-api-python-client"):
            fetch_videos(
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 2, 1, tzinfo=timezone.utc),
            )


def test_build_queries_dedupe_duplicate_channel_terms():
    """Duplicate terms in _CHANNEL_FOCUSED_TERMS collapse via _dedupe_pairs (continue branch)."""
    with patch.object(fetcher_mod, "_CHANNEL_FOCUSED_TERMS", ["C++", "C++"]):
        pairs = fetcher_mod._build_queries("CppCon")
    assert len(pairs) == 1
    assert pairs[0][0] == "C++"


def test_fetch_search_page_passes_page_token_and_channel_id():
    youtube = MagicMock()
    youtube.search.return_value.list.return_value.execute = MagicMock(
        return_value={"items": [], "nextPageToken": None}
    )
    fetcher_mod._fetch_search_page(
        youtube, "q", "chan123", "after", "before", "nextTok"
    )
    kwargs = youtube.search.return_value.list.call_args.kwargs
    assert kwargs["pageToken"] == "nextTok"
    assert kwargs["channelId"] == "chan123"


def test_format_video_data_missing_snippet_and_statistics():
    vd = {"id": "thin1", "snippet": {}, "statistics": {}, "contentDetails": {}}
    out = fetcher_mod._format_video_data(vd, search_term="s")
    assert out["video_id"] == "thin1"
    assert out["title"] == ""
    assert out["duration_seconds"] == 0
    assert out["view_count"] is None


@override_settings(YOUTUBE_API_KEY="k")
def test_process_one_channel_query_pagination_two_pages():
    youtube = MagicMock()
    page = {"n": 0}

    def search_execute():
        page["n"] += 1
        if page["n"] == 1:
            return {
                "items": [
                    {"id": {"kind": "youtube#video", "videoId": "pg1"}},
                ],
                "nextPageToken": "t2",
            }
        return {
            "items": [
                {"id": {"kind": "youtube#video", "videoId": "pg2"}},
            ],
            "nextPageToken": None,
        }

    search_mock = MagicMock(side_effect=search_execute)
    youtube.search.return_value.list.return_value.execute = search_mock

    def video_execute():
        call = youtube.videos.return_value.list.call_args
        ids = call.kwargs["id"].split(",")
        items = []
        for vid in ids:
            items.append(
                {
                    "id": vid,
                    "snippet": {"title": vid},
                    "statistics": {},
                    "contentDetails": {"duration": "PT30S"},
                }
            )
        return {"items": items}

    youtube.videos.return_value.list.return_value.execute = video_execute

    seen: set[str] = set()
    with patch.object(fetcher_mod.time, "sleep"):
        out = fetcher_mod._process_one_channel_query(
            youtube,
            "q",
            None,
            "a",
            "b",
            seen,
            min_duration_seconds=0,
        )
    assert len(out) == 2
    assert {row["video_id"] for row in out} == {"pg1", "pg2"}
    assert search_mock.call_count == 2


def test_process_one_channel_query_skips_detail_row_with_empty_id():
    youtube = MagicMock()
    youtube.search.return_value.list.return_value.execute = MagicMock(
        return_value={
            "items": [{"id": {"kind": "youtube#video", "videoId": "ghost"}}],
            "nextPageToken": None,
        }
    )
    youtube.videos.return_value.list.return_value.execute = MagicMock(
        return_value={
            "items": [
                {
                    "id": "",
                    "snippet": {},
                    "statistics": {},
                    "contentDetails": {"duration": "PT1M"},
                }
            ]
        }
    )
    seen: set[str] = set()
    with patch.object(fetcher_mod.time, "sleep"):
        out = fetcher_mod._process_one_channel_query(
            youtube,
            "q",
            None,
            "a",
            "b",
            seen,
            min_duration_seconds=0,
        )
    assert out == []


def test_process_one_channel_query_non_video_search_items_no_video_list_call():
    youtube = MagicMock()
    youtube.search.return_value.list.return_value.execute = MagicMock(
        return_value={
            "items": [
                {"id": {"kind": "youtube#playlist", "playlistId": "PL1"}},
            ],
            "nextPageToken": None,
        }
    )
    vid_exec = MagicMock(return_value={"items": []})
    youtube.videos.return_value.list.return_value.execute = vid_exec
    seen: set[str] = set()
    with patch.object(fetcher_mod.time, "sleep"):
        out = fetcher_mod._process_one_channel_query(
            youtube,
            "q",
            None,
            "a",
            "b",
            seen,
            min_duration_seconds=0,
        )
    assert out == []
    vid_exec.assert_not_called()


def test_process_one_channel_query_breaks_when_search_returns_none():
    youtube = MagicMock()
    youtube.search.return_value.list.return_value.execute = MagicMock(return_value=None)
    seen: set[str] = set()
    with patch.object(fetcher_mod.time, "sleep"):
        out = fetcher_mod._process_one_channel_query(
            youtube,
            "q",
            None,
            "a",
            "b",
            seen,
            min_duration_seconds=0,
        )
    assert out == []
