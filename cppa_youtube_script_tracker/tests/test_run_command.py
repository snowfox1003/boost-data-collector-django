"""Tests for run_cppa_youtube_script_tracker management command."""

import json
import shutil
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.test.utils import override_settings

from cppa_youtube_script_tracker.management.commands.run_cppa_youtube_script_tracker import (
    CppaYoutubeScriptTrackerCollector,
    Command,
    _enrich_speakers_from_transcript,
    _move_to_raw,
    _persist_fetched_video,
    _persist_video,
    _process_queue,
    _read_text_file,
    _resolve_end_time,
    _resolve_start_time,
    _run_phase_2,
    _run_phase_3,
    _run_pinecone_sync,
)
from cppa_youtube_script_tracker.models import YouTubeChannel, YouTubeVideo

_CMD = "cppa_youtube_script_tracker.management.commands.run_cppa_youtube_script_tracker"


@pytest.mark.django_db
def test_resolve_start_time_explicit():
    dt = _resolve_start_time("2020-05-01T12:00:00Z", dry_run=False)
    assert dt.tzinfo == timezone.utc


@pytest.mark.django_db
def test_resolve_start_time_from_db():
    YouTubeVideo.objects.create(
        video_id="dbv",
        title="t",
        published_at=datetime(2022, 3, 3, tzinfo=timezone.utc),
    )
    dt = _resolve_start_time("", dry_run=False)
    assert dt.year == 2022


@pytest.mark.django_db
def test_resolve_start_time_dry_run_skips_db():
    YouTubeVideo.objects.create(
        video_id="dbv2",
        title="t",
        published_at=datetime(2022, 3, 3, tzinfo=timezone.utc),
    )
    dt = _resolve_start_time("", dry_run=True)
    assert dt.year == 2015


@override_settings(YOUTUBE_DEFAULT_PUBLISHED_AFTER="2018-07-01T00:00:00Z")
@pytest.mark.django_db
def test_resolve_start_time_settings_default():
    dt = _resolve_start_time("", dry_run=True)
    assert dt.year == 2018


def test_resolve_end_time_default_now():
    dt = _resolve_end_time("")
    assert dt.tzinfo == timezone.utc


def test_resolve_end_time_explicit():
    dt = _resolve_end_time("2021-01-02T00:00:00Z")
    assert dt.year == 2021


@pytest.mark.django_db
def test_persist_video_skips_empty_id():
    created, skipped = _persist_video({"video_id": ""})
    assert created is False and skipped is True


@pytest.mark.django_db
def test_persist_video_creates(monkeypatch):
    monkeypatch.setattr(f"{_CMD}.resolve_speakers", lambda **_: ["Speaker"])
    data = {
        "video_id": "newone",
        "channel_id": "ch99",
        "channel_title": "CppCon",
        "title": "Talk",
        "description": "",
        "tags": ["meta"],
    }
    created, skipped = _persist_video(data)
    assert skipped is False
    assert YouTubeVideo.objects.filter(video_id="newone").exists()


@pytest.mark.django_db
def test_process_queue_moves_file(tmp_path, monkeypatch):
    meta = tmp_path / "metadata"
    meta.mkdir(parents=True)
    qfile = meta / "vqueue.json"
    qfile.write_text(
        json.dumps(
            {
                "video_id": "q1",
                "channel_id": "c1",
                "channel_title": "CppCon",
                "title": "Hi",
                "description": "",
                "tags": [],
            }
        ),
        encoding="utf-8",
    )

    raw_meta = tmp_path / "raw_meta"
    raw_meta.mkdir(parents=True)

    monkeypatch.setattr(f"{_CMD}.iter_metadata_queue_jsons", lambda: [qfile])
    monkeypatch.setattr(f"{_CMD}.resolve_speakers", lambda **_: ["S"])
    monkeypatch.setattr(
        f"{_CMD}.get_raw_metadata_path", lambda vid: raw_meta / f"{vid}.json"
    )

    processed, skipped = _process_queue()
    assert processed == 1
    assert not qfile.exists()
    assert (raw_meta / "q1.json").exists()


def test_move_to_raw_failure_logged(tmp_path, monkeypatch, caplog):
    import logging

    caplog.set_level(logging.WARNING)
    bad = tmp_path / "nope.json"
    bad.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        f"{_CMD}.get_raw_metadata_path", lambda _vid: tmp_path / "out.json"
    )

    def _move_fail(*_a, **_k):
        raise OSError("fail")

    monkeypatch.setattr(shutil, "move", _move_fail)

    _move_to_raw("vid", bad)
    assert bad.exists()


def test_read_text_file_missing():
    assert _read_text_file(str(Path("/nonexistent/path/file.txt"))) == ""


@pytest.mark.django_db
def test_enrich_speakers_from_transcript(tmp_path):
    ch = YouTubeChannel.objects.create(
        channel_id="c55",
        channel_title="Chan",
    )
    video = YouTubeVideo.objects.create(
        video_id="enr1",
        channel=ch,
        title="T",
        description="",
    )
    tr = tmp_path / "t.vtt"
    tr.write_text(
        "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nMy name is Pat Speaker\n",
        encoding="utf-8",
    )
    _enrich_speakers_from_transcript(video, str(tr))
    video.refresh_from_db()
    from cppa_youtube_script_tracker.models import YouTubeVideoSpeaker

    assert YouTubeVideoSpeaker.objects.filter(video=video).exists()


@pytest.mark.django_db
def test_run_phase_2_counts(monkeypatch):
    monkeypatch.setattr(
        f"{_CMD}.fetch_videos",
        lambda **_: [
            {
                "video_id": "f1",
                "channel_id": "c1",
                "channel_title": "CppCon",
                "title": "T",
                "description": "",
                "tags": [],
            }
        ],
    )
    monkeypatch.setattr(f"{_CMD}.resolve_speakers", lambda **_: ["X"])
    monkeypatch.setattr(f"{_CMD}._persist_fetched_video", lambda _d: (True, False))
    c, s = _run_phase_2(
        datetime(2024, 1, 1, tzinfo=timezone.utc),
        datetime(2024, 2, 1, tzinfo=timezone.utc),
        "CppCon",
    )
    assert c == 1 and s == 0


@pytest.mark.django_db
def test_run_phase_3_updates(monkeypatch, tmp_path):
    YouTubeVideo.objects.create(video_id="p3", title="t", has_transcript=False)
    monkeypatch.setattr(f"{_CMD}.get_raw_transcripts_dir", lambda: tmp_path)
    out_vtt = tmp_path / "p3.en.vtt"
    out_vtt.write_text("WEBVTT", encoding="utf-8")

    monkeypatch.setattr(f"{_CMD}.download_vtt", lambda *_a, **_k: out_vtt)
    monkeypatch.setattr(
        f"{_CMD}._enrich_speakers_from_transcript", lambda *_a, **_k: None
    )

    ok, fail = _run_phase_3()
    assert ok == 1 and fail == 0
    assert YouTubeVideo.objects.get(video_id="p3").has_transcript is True


def test_run_pinecone_sync_skips_without_app(caplog):
    import logging

    caplog.set_level(logging.WARNING)
    _run_pinecone_sync("", "ns")
    assert any("skipped" in r.message.lower() for r in caplog.records)


def test_run_pinecone_sync_calls_command():
    with patch(f"{_CMD}.call_command") as m:
        _run_pinecone_sync("app", "ns")
    m.assert_called_once()


def test_collector_dry_run_short_circuits(monkeypatch):
    stdout = StringIO()
    cmd = Command(stdout=stdout, stderr=StringIO())
    phases = []

    monkeypatch.setattr(cmd, "_phase_1", lambda dry: phases.append(("p1", dry)))

    collector = CppaYoutubeScriptTrackerCollector(
        cmd=cmd,
        options={
            "start_time": "",
            "end_time": "",
            "channel_title": "",
            "dry_run": True,
            "skip_transcript": False,
        },
    )
    collector.run()
    assert phases == [("p1", True)]
    out = stdout.getvalue()
    assert "Dry run" in out


@pytest.mark.django_db
def test_command_phase_2_no_videos_warning(monkeypatch):
    stdout = StringIO()
    cmd = Command(stdout=stdout, stderr=StringIO())
    monkeypatch.setattr(f"{_CMD}._run_phase_2", lambda *a: (0, 0))
    cmd._phase_2(
        datetime(2024, 1, 1, tzinfo=timezone.utc),
        datetime(2024, 2, 1, tzinfo=timezone.utc),
        "",
    )
    assert "no new videos" in stdout.getvalue().lower()


def test_collector_sync_pinecone_invokes_run(monkeypatch):
    stdout = StringIO()
    cmd = Command(stdout=stdout, stderr=StringIO())
    spy = MagicMock()
    monkeypatch.setattr(f"{_CMD}._run_pinecone_sync", spy)
    collector = CppaYoutubeScriptTrackerCollector(
        cmd=cmd,
        options={
            "dry_run": False,
            "pinecone_app_id": "myapp",
            "pinecone_namespace": "mynamespace",
        },
    )
    collector.sync_pinecone()
    spy.assert_called_once_with(app_id="myapp", namespace="mynamespace")


@pytest.mark.django_db
def test_collector_sync_pinecone_skips_on_dry_run(monkeypatch):
    spy = MagicMock()
    monkeypatch.setattr(f"{_CMD}._run_pinecone_sync", spy)
    collector = CppaYoutubeScriptTrackerCollector(
        cmd=Command(stdout=StringIO(), stderr=StringIO()),
        options={
            "dry_run": True,
            "pinecone_app_id": "x",
            "pinecone_namespace": "y",
        },
    )
    collector.sync_pinecone()
    spy.assert_not_called()


@pytest.mark.django_db
def test_command_handle_invokes_collector_phases():
    collector = MagicMock()
    out = StringIO()
    err = StringIO()
    with patch.object(Command, "get_collector", lambda self, **kw: collector):
        call_command(
            "run_cppa_youtube_script_tracker",
            stdout=out,
            stderr=err,
            skip_transcript=True,
            dry_run=True,
        )
    collector.run.assert_called_once()
    collector.sync_pinecone.assert_called_once()


@pytest.mark.django_db
def test_command_phase_outputs(monkeypatch):
    stdout = StringIO()
    cmd = Command(stdout=stdout, stderr=StringIO())
    monkeypatch.setattr(cmd, "_phase_1", lambda dry: None)
    monkeypatch.setattr(cmd, "_phase_2", lambda *a: None)
    monkeypatch.setattr(cmd, "_phase_3", lambda skip: None)

    collector = CppaYoutubeScriptTrackerCollector(
        cmd=cmd,
        options={
            "start_time": "2024-01-01T00:00:00Z",
            "end_time": "2024-02-01T00:00:00Z",
            "channel_title": "",
            "dry_run": False,
            "skip_transcript": True,
            "pinecone_app_id": "",
            "pinecone_namespace": "",
        },
    )
    collector.run()
    assert "Phase 2" in stdout.getvalue()


@pytest.mark.django_db
def test_run_phase_3_download_vtt_returns_none(monkeypatch, tmp_path):
    YouTubeVideo.objects.create(video_id="nofile", title="t", has_transcript=False)
    monkeypatch.setattr(f"{_CMD}.get_raw_transcripts_dir", lambda: tmp_path)
    monkeypatch.setattr(f"{_CMD}.download_vtt", lambda *_a, **_k: None)

    ok, fail = _run_phase_3()
    assert ok == 0 and fail == 1
    assert YouTubeVideo.objects.get(video_id="nofile").has_transcript is False


@pytest.mark.django_db
def test_run_phase_3_download_vtt_raises(monkeypatch, tmp_path, caplog):
    import logging

    YouTubeVideo.objects.create(video_id="boom", title="t", has_transcript=False)
    monkeypatch.setattr(f"{_CMD}.get_raw_transcripts_dir", lambda: tmp_path)

    def _boom(*_a, **_k):
        raise RuntimeError("yt-dlp simulated failure")

    monkeypatch.setattr(f"{_CMD}.download_vtt", _boom)
    caplog.set_level(logging.ERROR)

    ok, fail = _run_phase_3()
    assert ok == 0 and fail == 1
    assert any("transcript download failed" in r.getMessage() for r in caplog.records)


@pytest.mark.django_db
def test_persist_fetched_video_exception_leaves_queue_json(tmp_path, monkeypatch):
    meta_dir = tmp_path / "queue"
    meta_dir.mkdir(parents=True)

    monkeypatch.setattr(
        f"{_CMD}.get_metadata_queue_path", lambda vid: meta_dir / f"{vid}.json"
    )
    monkeypatch.setattr(
        f"{_CMD}._persist_video",
        lambda _data: (_ for _ in ()).throw(RuntimeError("db")),
    )

    created, skipped = _persist_fetched_video(
        {
            "video_id": "qvid",
            "channel_id": "c1",
            "channel_title": "CppCon",
            "title": "T",
            "description": "",
            "tags": [],
        }
    )
    assert created is False and skipped is True
    qpath = meta_dir / "qvid.json"
    assert qpath.exists()
    payload = json.loads(qpath.read_text(encoding="utf-8"))
    assert payload["video_id"] == "qvid"


@pytest.mark.django_db
def test_process_queue_persist_exception_leaves_queue_file(tmp_path, monkeypatch):
    meta = tmp_path / "metadata"
    meta.mkdir(parents=True)
    qfile = meta / "baditem.json"
    qfile.write_text(
        json.dumps(
            {
                "video_id": "bad1",
                "channel_id": "c1",
                "channel_title": "CppCon",
                "title": "Hi",
                "description": "",
                "tags": [],
            }
        ),
        encoding="utf-8",
    )
    raw_meta = tmp_path / "raw_meta"
    raw_meta.mkdir(parents=True)

    monkeypatch.setattr(f"{_CMD}.iter_metadata_queue_jsons", lambda: [qfile])

    def _persist_raises(_item):
        raise RuntimeError("persist boom")

    monkeypatch.setattr(f"{_CMD}._persist_video", _persist_raises)
    monkeypatch.setattr(
        f"{_CMD}.get_raw_metadata_path", lambda vid: raw_meta / f"{vid}.json"
    )

    processed, skipped = _process_queue()
    assert processed == 1
    assert skipped >= 1
    assert qfile.exists()


@pytest.mark.django_db
def test_enrich_speakers_from_transcript_empty_file(tmp_path):
    ch = YouTubeChannel.objects.create(channel_id="c66", channel_title="Chan")
    video = YouTubeVideo.objects.create(
        video_id="enr_empty",
        channel=ch,
        title="T",
        description="",
    )
    tr = tmp_path / "empty.vtt"
    tr.write_text("", encoding="utf-8")
    from cppa_youtube_script_tracker.models import YouTubeVideoSpeaker

    before = YouTubeVideoSpeaker.objects.filter(video=video).count()
    _enrich_speakers_from_transcript(video, str(tr))
    assert YouTubeVideoSpeaker.objects.filter(video=video).count() == before


@pytest.mark.django_db
def test_enrich_speakers_from_transcript_resolve_empty(monkeypatch, tmp_path):
    ch = YouTubeChannel.objects.create(channel_id="c77", channel_title="Chan")
    video = YouTubeVideo.objects.create(
        video_id="enr_none",
        channel=ch,
        title="T",
        description="",
    )
    tr = tmp_path / "some.vtt"
    tr.write_text("WEBVTT\n\nnote\n", encoding="utf-8")
    monkeypatch.setattr(f"{_CMD}.resolve_speakers", lambda **_k: [])

    _enrich_speakers_from_transcript(video, str(tr))


@pytest.mark.django_db
def test_enrich_speakers_from_transcript_link_failure_logged(
    monkeypatch, tmp_path, caplog
):
    import logging

    ch = YouTubeChannel.objects.create(channel_id="c88", channel_title="Chan")
    video = YouTubeVideo.objects.create(
        video_id="enr_warn",
        channel=ch,
        title="T",
        description="",
    )
    tr = tmp_path / "w.vtt"
    tr.write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nX\n", encoding="utf-8")
    monkeypatch.setattr(f"{_CMD}.resolve_speakers", lambda **_k: ["Pat"])
    calls = {"n": 0}

    def _bad_speaker(*_a, **_k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("speaker create failed")
        from cppa_user_tracker.services import get_or_create_youtube_speaker as real

        return real(*_a, **_k)

    monkeypatch.setattr(f"{_CMD}.get_or_create_youtube_speaker", _bad_speaker)
    caplog.set_level(logging.WARNING)

    _enrich_speakers_from_transcript(video, str(tr))
    assert any("could not link speaker" in r.getMessage() for r in caplog.records)


@pytest.mark.django_db
def test_command_phase_3_skip_transcript_stdout():
    stdout = StringIO()
    cmd = Command(stdout=stdout, stderr=StringIO())
    cmd._phase_3(skip_transcript=True)
    assert "skipped" in stdout.getvalue().lower()


@pytest.mark.django_db
def test_command_phase_3_stdout_ok_fail(monkeypatch):
    stdout = StringIO()
    cmd = Command(stdout=stdout, stderr=StringIO())
    monkeypatch.setattr(f"{_CMD}._run_phase_3", lambda: (2, 3))
    cmd._phase_3(skip_transcript=False)
    out = stdout.getvalue()
    assert "2" in out and "3" in out and "downloaded" in out.lower()


def test_run_pinecone_sync_skips_empty_namespace(caplog):
    import logging

    caplog.set_level(logging.WARNING)
    _run_pinecone_sync("myapp", "")
    assert any("namespace" in r.message.lower() for r in caplog.records)


def test_run_pinecone_sync_call_command_exception_logged(caplog):
    import logging

    def _raise(*_a, **_k):
        raise RuntimeError("pinecone down")

    caplog.set_level(logging.WARNING)
    with patch(f"{_CMD}.call_command", side_effect=_raise):
        _run_pinecone_sync("app", "ns")
    assert any("pinecone" in r.message.lower() for r in caplog.records)


@pytest.mark.django_db
def test_collector_propagates_unhandled_phase_error(monkeypatch):
    stdout = StringIO()
    cmd = Command(stdout=stdout, stderr=StringIO())

    monkeypatch.setattr(cmd, "_phase_1", lambda _dry: None)

    def _boom(*_a, **_k):
        raise RuntimeError("phase2 failed")

    monkeypatch.setattr(cmd, "_phase_2", _boom)

    collector = CppaYoutubeScriptTrackerCollector(
        cmd=cmd,
        options={
            "start_time": "2024-01-01T00:00:00Z",
            "end_time": "2024-02-01T00:00:00Z",
            "channel_title": "",
            "dry_run": False,
            "skip_transcript": True,
        },
    )
    with pytest.raises(RuntimeError, match="phase2 failed"):
        collector.run()


@pytest.mark.django_db
def test_persist_video_skips_blank_tags(monkeypatch):
    monkeypatch.setattr(f"{_CMD}.resolve_speakers", lambda **_: ["S"])
    created, skipped = _persist_video(
        {
            "video_id": "tagblank",
            "channel_id": "c1",
            "channel_title": "CppCon",
            "title": "T",
            "description": "",
            "tags": ["", "  ", "real"],
        }
    )
    assert skipped is False
    from cppa_youtube_script_tracker.models import YouTubeVideoTags

    links = YouTubeVideoTags.objects.filter(youtube_video_id="tagblank")
    assert links.count() == 1


@pytest.mark.django_db
def test_process_queue_json_read_failure_logged(tmp_path, monkeypatch, caplog):
    import logging

    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(f"{_CMD}.iter_metadata_queue_jsons", lambda: [bad])
    caplog.set_level(logging.ERROR)
    processed, _ = _process_queue()
    assert processed == 0
    assert any("failed to read" in r.getMessage() for r in caplog.records)


@pytest.mark.django_db
def test_process_queue_skipped_video_increments_counter(tmp_path, monkeypatch):
    meta = tmp_path / "metadata"
    meta.mkdir(parents=True)
    qfile = meta / "skipcount.json"
    qfile.write_text(
        json.dumps(
            {
                "video_id": "",
                "channel_id": "c1",
                "channel_title": "CppCon",
                "title": "Hi",
                "description": "",
                "tags": [],
            }
        ),
        encoding="utf-8",
    )
    raw_meta = tmp_path / "raw_meta"
    raw_meta.mkdir(parents=True)
    monkeypatch.setattr(f"{_CMD}.iter_metadata_queue_jsons", lambda: [qfile])
    monkeypatch.setattr(
        f"{_CMD}.get_raw_metadata_path", lambda vid: raw_meta / f"{vid}.json"
    )
    processed, skipped = _process_queue()
    assert processed == 1
    assert skipped >= 1


@pytest.mark.django_db
def test_persist_fetched_video_empty_video_id():
    created, skipped = _persist_fetched_video({"video_id": ""})
    assert created is False and skipped is True


@pytest.mark.django_db
def test_command_phase_1_writes_summary(monkeypatch):
    stdout = StringIO()
    cmd = Command(stdout=stdout, stderr=StringIO())
    monkeypatch.setattr(f"{_CMD}._process_queue", lambda: (2, 1))
    cmd._phase_1(dry_run=False)
    out = stdout.getvalue()
    assert "Phase 1" in out and "2" in out and "1" in out


@pytest.mark.django_db
def test_command_phase_2_success_branch(monkeypatch):
    stdout = StringIO()
    cmd = Command(stdout=stdout, stderr=StringIO())
    monkeypatch.setattr(f"{_CMD}._run_phase_2", lambda *a: (3, 2))
    cmd._phase_2(
        datetime(2024, 1, 1, tzinfo=timezone.utc),
        datetime(2024, 2, 1, tzinfo=timezone.utc),
        "",
    )
    out = stdout.getvalue().lower()
    assert "created" in out and "skipped" in out


@pytest.mark.django_db
def test_run_phase_2_counts_skipped(monkeypatch):
    monkeypatch.setattr(
        f"{_CMD}.fetch_videos",
        lambda **_: [
            {
                "video_id": "a",
                "channel_id": "c",
                "channel_title": "CppCon",
                "title": "A",
            },
            {
                "video_id": "b",
                "channel_id": "c",
                "channel_title": "CppCon",
                "title": "B",
            },
        ],
    )
    monkeypatch.setattr(f"{_CMD}.resolve_speakers", lambda **_: ["X"])
    monkeypatch.setattr(
        f"{_CMD}._persist_fetched_video",
        lambda d: (True, False) if d["video_id"] == "a" else (False, True),
    )
    c, s = _run_phase_2(
        datetime(2024, 1, 1, tzinfo=timezone.utc),
        datetime(2024, 2, 1, tzinfo=timezone.utc),
        "CppCon",
    )
    assert c == 1 and s == 1


@pytest.mark.django_db
def test_persist_video_logs_validation_error(monkeypatch, caplog):
    import logging
    from django.core.exceptions import ValidationError

    caplog.set_level(logging.WARNING)
    monkeypatch.setattr(
        f"{_CMD}.get_or_create_video",
        lambda *_a, **_k: (_ for _ in ()).throw(ValidationError("bad")),
    )
    monkeypatch.setattr(f"{_CMD}.get_or_create_channel", lambda *_a, **_k: None)

    created, skipped = _persist_video(
        {
            "video_id": "valerr",
            "channel_id": "",
            "channel_title": "",
            "title": "T",
            "description": "",
            "tags": [],
        }
    )
    assert created is False and skipped is True
    assert any("validation error" in r.message.lower() for r in caplog.records)
