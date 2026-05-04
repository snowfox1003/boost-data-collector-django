"""Tests for cppa_youtube_script_tracker.transcript."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cppa_youtube_script_tracker.transcript import download_vtt


def test_download_vtt_import_error():
    real_import = __import__

    def fake_import(name, globals_=None, locals_=None, fromlist=(), level=0):
        if name == "yt_dlp":
            raise ImportError("no yt_dlp")
        return real_import(name, globals_, locals_, fromlist, level)

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(ImportError, match="yt-dlp"):
            download_vtt("vid", Path("/tmp"))


def _make_ytdl_context(mock_ytdl):
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_ytdl
    mock_ctx.__exit__.return_value = None
    return mock_ctx


def test_download_vtt_success_expected_path(tmp_path):
    mock_ytdl = MagicMock()

    def _download(_urls):
        (tmp_path / "abc.en.vtt").write_text("WEBVTT", encoding="utf-8")

    mock_ytdl.download.side_effect = _download

    with patch("yt_dlp.YoutubeDL", return_value=_make_ytdl_context(mock_ytdl)):
        out = download_vtt("abc", tmp_path)
    assert out == tmp_path / "abc.en.vtt"


def test_download_vtt_fallback_glob(tmp_path):
    mock_ytdl = MagicMock()

    def _download(_urls):
        (tmp_path / "abc.en-auto.vtt").write_text("WEBVTT", encoding="utf-8")

    mock_ytdl.download.side_effect = _download

    with patch("yt_dlp.YoutubeDL", return_value=_make_ytdl_context(mock_ytdl)):
        out = download_vtt("abc", tmp_path)
    assert out == tmp_path / "abc.en-auto.vtt"


def test_download_vtt_ytdlp_error_returns_none(tmp_path):
    mock_ytdl = MagicMock()
    mock_ytdl.download.side_effect = RuntimeError("boom")

    with patch("yt_dlp.YoutubeDL", return_value=_make_ytdl_context(mock_ytdl)):
        assert download_vtt("abc", tmp_path) is None


def test_download_vtt_no_file_returns_none(tmp_path):
    mock_ytdl = MagicMock()
    mock_ytdl.download.return_value = None

    with patch("yt_dlp.YoutubeDL", return_value=_make_ytdl_context(mock_ytdl)):
        assert download_vtt("missingvid", tmp_path) is None


def test_download_vtt_passes_cookies_file(tmp_path):
    mock_ytdl = MagicMock()

    def _download(_urls):
        (tmp_path / "z.en.vtt").write_text("WEBVTT", encoding="utf-8")

    mock_ytdl.download.side_effect = _download
    captured = {}

    def ctor(opts):
        captured.update(opts)
        return _make_ytdl_context(mock_ytdl)

    with patch("yt_dlp.YoutubeDL", side_effect=ctor):
        download_vtt("z", tmp_path, cookies_file="/cookies.txt")

    assert captured.get("cookiefile") == "/cookies.txt"
