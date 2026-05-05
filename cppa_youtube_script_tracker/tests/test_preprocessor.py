"""Tests for cppa_youtube_script_tracker.preprocessor."""

from pathlib import Path
from unittest.mock import patch

import pytest
from django.utils import timezone
from model_bakery import baker

from cppa_youtube_script_tracker.models import (
    YouTubeChannel,
    YouTubeVideo,
    YouTubeVideoSpeaker,
)
from cppa_youtube_script_tracker.preprocessor import (
    _normalize_failed_ids,
    _read_vtt,
    preprocess_youtube_for_pinecone,
)


@pytest.mark.django_db
def test_preprocess_builds_document_with_channel_and_transcript(tmp_path):
    ch = baker.make(YouTubeChannel, channel_id="chx", channel_title="Chan")
    video = baker.make(
        YouTubeVideo,
        video_id="vid99",
        channel=ch,
        title="Hello",
        description="World",
        published_at=timezone.now(),
        has_transcript=True,
        transcript_path=str(tmp_path / "missing.vtt"),
    )
    speaker = baker.make(
        "cppa_user_tracker.YoutubeSpeaker",
        external_id="sp1",
        display_name="Ann",
    )
    baker.make(YouTubeVideoSpeaker, video=video, speaker=speaker)

    docs, chunked = preprocess_youtube_for_pinecone([], None)
    assert chunked is False
    assert len(docs) == 1
    assert "Hello" in docs[0]["content"]
    assert "Ann" in docs[0]["content"]
    assert docs[0]["metadata"]["doc_id"] == "youtube-vid99"


@pytest.mark.django_db
def test_preprocess_reads_vtt_when_present(tmp_path):
    vtt = tmp_path / "t.vtt"
    vtt.write_text(
        "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello cue\n",
        encoding="utf-8",
    )
    _ = baker.make(
        YouTubeVideo,
        video_id="vtt1",
        title="T",
        published_at=timezone.now(),
        has_transcript=True,
        transcript_path=str(vtt),
    )

    docs, _ = preprocess_youtube_for_pinecone([], None)
    assert "Hello cue" in docs[0]["content"]


@pytest.mark.django_db
def test_preprocess_skips_empty_content():
    baker.make(
        YouTubeVideo,
        video_id="empty1",
        title="",
        description="",
        published_at=None,
        has_transcript=False,
    )
    docs, _ = preprocess_youtube_for_pinecone([], None)
    assert docs == []


@pytest.mark.django_db
def test_preprocess_incremental_and_failed_ids():
    old = timezone.now() - timezone.timedelta(days=2)
    recent = timezone.now() - timezone.timedelta(hours=1)

    baker.make(
        YouTubeVideo,
        video_id="old_v",
        title="Old",
        published_at=old,
        updated_at=old,
    )
    baker.make(
        YouTubeVideo,
        video_id="new_v",
        title="New",
        published_at=recent,
        updated_at=recent,
    )

    docs, _ = preprocess_youtube_for_pinecone([], final_sync_at=old)
    ids = {d["metadata"]["doc_id"] for d in docs}
    assert "youtube-new_v" in ids
    assert "youtube-old_v" not in ids

    docs2, _ = preprocess_youtube_for_pinecone(["old_v"], final_sync_at=old)
    ids2 = {d["metadata"]["doc_id"] for d in docs2}
    assert "youtube-old_v" in ids2


def test_normalize_failed_ids_trims_and_dedupes():
    assert _normalize_failed_ids([" a ", "", "a", "b"]) == ["a", "b"]


def test_read_vtt_skips_timestamp_and_cue_settings(tmp_path):
    vtt = tmp_path / "x.vtt"
    vtt.write_text(
        "WEBVTT\n\nNOTE comment\n\n"
        "00:00:00.000 --> 00:00:01.000\n"
        "Hello line\n"
        "align:start position:0%\n",
        encoding="utf-8",
    )
    assert _read_vtt(str(vtt)) == "Hello line"


@pytest.mark.django_db
def test_preprocess_vtt_read_oserror_returns_empty(tmp_path):
    vtt = tmp_path / "bad.vtt"
    vtt.write_text("WEBVTT", encoding="utf-8")
    _ = baker.make(
        YouTubeVideo,
        video_id="os1",
        title="Only title",
        published_at=timezone.now(),
        has_transcript=True,
        transcript_path=str(vtt),
    )

    with patch.object(Path, "read_text", side_effect=OSError("denied")):
        docs, _ = preprocess_youtube_for_pinecone([], None)

    assert len(docs) == 1
    assert "Only title" in docs[0]["content"]
    assert "Transcript" not in docs[0]["content"]
