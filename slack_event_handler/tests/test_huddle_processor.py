"""Tests for slack_event_handler.utils.huddle_processor."""

from unittest.mock import MagicMock, patch

import pytest

from slack_event_handler.utils import huddle_processor


@pytest.mark.django_db
def test_process_huddle_canvas_fetch_fails():
    with patch(
        "slack_event_handler.utils.huddle_processor.fetch_huddle_transcript",
        return_value=None,
    ):
        out = huddle_processor.process_huddle_canvas("F123")
    assert out == {"success": False}


@pytest.mark.django_db
def test_process_huddle_canvas_not_ok():
    with patch(
        "slack_event_handler.utils.huddle_processor.fetch_huddle_transcript",
        return_value={"ok": False},
    ):
        out = huddle_processor.process_huddle_canvas("F123")
    assert out == {"success": False}


@pytest.mark.django_db
def test_process_huddle_canvas_no_download_url():
    with patch(
        "slack_event_handler.utils.huddle_processor.fetch_huddle_transcript",
        return_value={"ok": True, "file": {}},
    ):
        out = huddle_processor.process_huddle_canvas("F123")
    assert out == {"success": False}


@pytest.mark.django_db
def test_process_huddle_canvas_fetcher_init_fails(tmp_path):
    with patch(
        "slack_event_handler.utils.huddle_processor.fetch_huddle_transcript",
        return_value={
            "ok": True,
            "file": {"url_private_download": "https://x", "name": "a.html"},
        },
    ):
        with patch(
            "slack_event_handler.utils.huddle_processor.get_data_dir",
            return_value=tmp_path,
        ):
            with patch(
                "slack_event_handler.utils.huddle_processor.SlackFetcher",
                side_effect=ValueError("no token"),
            ):
                out = huddle_processor.process_huddle_canvas("F999")
    assert out == {"success": False}


@pytest.mark.django_db
def test_process_huddle_canvas_download_fails(tmp_path):
    mock_fetcher = MagicMock()
    mock_fetcher.download_file.return_value = None
    with patch(
        "slack_event_handler.utils.huddle_processor.fetch_huddle_transcript",
        return_value={
            "ok": True,
            "file": {"url_private_download": "https://x", "name": "a.html"},
        },
    ):
        with patch(
            "slack_event_handler.utils.huddle_processor.get_data_dir",
            return_value=tmp_path,
        ):
            with patch(
                "slack_event_handler.utils.huddle_processor.SlackFetcher",
                return_value=mock_fetcher,
            ):
                out = huddle_processor.process_huddle_canvas("F1")
    assert out == {"success": False}


@pytest.mark.django_db
def test_process_huddle_canvas_markdown_fails(tmp_path):
    mock_fetcher = MagicMock()
    mock_fetcher.download_file.return_value = str(tmp_path / "a.html")
    (tmp_path / "a.html").write_text("x", encoding="utf-8")

    with patch(
        "slack_event_handler.utils.huddle_processor.fetch_huddle_transcript",
        return_value={
            "ok": True,
            "file": {"url_private_download": "https://x", "name": "a.html"},
        },
    ):
        with patch(
            "slack_event_handler.utils.huddle_processor.get_data_dir",
            return_value=tmp_path,
        ):
            with patch(
                "slack_event_handler.utils.huddle_processor.SlackFetcher",
                return_value=mock_fetcher,
            ):
                with patch(
                    "slack_event_handler.utils.huddle_processor.generate_huddle_markdown",
                    return_value=None,
                ):
                    out = huddle_processor.process_huddle_canvas("F1")
    assert out == {"success": False}


@pytest.mark.django_db
def test_process_huddle_canvas_missing_github_repo_settings(tmp_path, settings):
    settings.GITHUB_SLACK_HUDDLE_REPO_OWNER = ""
    settings.GITHUB_SLACK_HUDDLE_REPO_NAME = ""

    mock_fetcher = MagicMock()
    html = tmp_path / "F2" / "a.html"
    html.parent.mkdir(parents=True)
    html.write_text("<html/>", encoding="utf-8")
    mock_fetcher.download_file.return_value = str(html)

    with patch(
        "slack_event_handler.utils.huddle_processor.fetch_huddle_transcript",
        return_value={
            "ok": True,
            "file": {"url_private_download": "https://x", "name": "a.html"},
        },
    ):
        with patch(
            "slack_event_handler.utils.huddle_processor.get_data_dir",
            return_value=tmp_path,
        ):
            with patch(
                "slack_event_handler.utils.huddle_processor.SlackFetcher",
                return_value=mock_fetcher,
            ):
                with patch(
                    "slack_event_handler.utils.huddle_processor.generate_huddle_markdown",
                    return_value=str(tmp_path / "out.md"),
                ):
                    (tmp_path / "out.md").write_text("md", encoding="utf-8")
                    out = huddle_processor.process_huddle_canvas("F2")
    assert out == {"success": False}


@pytest.mark.django_db
def test_process_huddle_canvas_upload_fail(tmp_path, settings):
    settings.GITHUB_SLACK_HUDDLE_REPO_OWNER = "o"
    settings.GITHUB_SLACK_HUDDLE_REPO_NAME = "r"
    settings.GITHUB_DEFAULT_BRANCH = "main"

    mock_fetcher = MagicMock()
    work = tmp_path / "F3"
    work.mkdir(parents=True)
    html = work / "a.html"
    html.write_text("<html/>", encoding="utf-8")
    mock_fetcher.download_file.return_value = str(html)
    md_path = work / "t.md"
    md_path.write_text("md", encoding="utf-8")

    with patch(
        "slack_event_handler.utils.huddle_processor.fetch_huddle_transcript",
        return_value={
            "ok": True,
            "file": {"url_private_download": "https://x", "name": "a.html"},
        },
    ):
        with patch(
            "slack_event_handler.utils.huddle_processor.get_data_dir",
            return_value=tmp_path,
        ):
            with patch(
                "slack_event_handler.utils.huddle_processor.SlackFetcher",
                return_value=mock_fetcher,
            ):
                with patch(
                    "slack_event_handler.utils.huddle_processor.generate_huddle_markdown",
                    return_value=str(md_path),
                ):
                    with patch(
                        "slack_event_handler.utils.huddle_processor.upload_file",
                        return_value=False,
                    ):
                        out = huddle_processor.process_huddle_canvas("F3")
    assert out == {"success": False}


@pytest.mark.django_db
def test_process_huddle_canvas_success(tmp_path, settings):
    settings.GITHUB_SLACK_HUDDLE_REPO_OWNER = "acme"
    settings.GITHUB_SLACK_HUDDLE_REPO_NAME = "repo"
    settings.GITHUB_DEFAULT_BRANCH = "develop"

    mock_fetcher = MagicMock()
    work = tmp_path / "F4"
    work.mkdir(parents=True)
    html = work / "h.html"
    html.write_text("<html/>", encoding="utf-8")
    mock_fetcher.download_file.return_value = str(html)
    md_path = work / "doc.md"
    md_path.write_text("md", encoding="utf-8")

    with patch(
        "slack_event_handler.utils.huddle_processor.fetch_huddle_transcript",
        return_value={
            "ok": True,
            "file": {"url_private_download": "https://x", "name": "h.html"},
        },
    ):
        with patch(
            "slack_event_handler.utils.huddle_processor.get_data_dir",
            return_value=tmp_path,
        ):
            with patch(
                "slack_event_handler.utils.huddle_processor.SlackFetcher",
                return_value=mock_fetcher,
            ):
                with patch(
                    "slack_event_handler.utils.huddle_processor.generate_huddle_markdown",
                    return_value=str(md_path),
                ):
                    with patch(
                        "slack_event_handler.utils.huddle_processor.upload_file",
                        return_value=True,
                    ):
                        out = huddle_processor.process_huddle_canvas("F4")

    assert out["success"] is True
    assert "github.com/acme/repo/blob/develop/" in out["github_url"]
