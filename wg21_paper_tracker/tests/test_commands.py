"""Tests for wg21_paper_tracker management commands."""

from unittest.mock import MagicMock, patch

import pytest

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test.utils import override_settings

from wg21_paper_tracker.pipeline import TrackerPipelineResult


CMD_NAME = "import_wg21_metadata_from_csv"
RUN_TRACKER_CMD = "run_wg21_paper_tracker"


def test_import_wg21_metadata_from_csv_raises_when_csv_missing(tmp_path):
    """Command raises CommandError when CSV file does not exist."""
    csv_path = tmp_path / "nonexistent.csv"
    assert not csv_path.exists()

    with pytest.raises(CommandError, match=r"File not found:"):
        call_command(CMD_NAME, f"--csv-file={csv_path}")


@pytest.mark.django_db
def test_run_wg21_paper_tracker_posts_dispatch_when_enabled():
    """run_wg21_paper_tracker sends repository_dispatch with papers URL list."""
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 204
    mock_resp.text = ""

    with patch(
        "wg21_paper_tracker.collectors.run_tracker_pipeline",
        return_value=TrackerPipelineResult(
            new_paper_urls=("https://open-std.org/a.pdf", "https://open-std.org/b.pdf")
        ),
    ):
        with patch(
            "wg21_paper_tracker.collectors.requests.post",
            return_value=mock_resp,
        ) as m_post:
            with override_settings(
                WG21_GITHUB_DISPATCH_ENABLED=True,
                WG21_GITHUB_DISPATCH_REPO="myorg/convert-repo",
                WG21_GITHUB_DISPATCH_TOKEN="secret-token",
                WG21_GITHUB_DISPATCH_EVENT_TYPE="wg21_papers_convert",
            ):
                call_command(RUN_TRACKER_CMD)

    m_post.assert_called_once()
    assert m_post.call_args[0][0] == (
        "https://api.github.com/repos/myorg/convert-repo/dispatches"
    )
    body = m_post.call_args[1]["json"]
    assert body["event_type"] == "wg21_papers_convert"
    assert body["client_payload"] == {
        "papers": [
            "https://open-std.org/a.pdf",
            "https://open-std.org/b.pdf",
        ],
    }
    headers = m_post.call_args[1]["headers"]
    assert headers["Authorization"] == "Bearer secret-token"
    assert headers["Accept"] == "application/vnd.github+json"


@pytest.mark.django_db
def test_run_wg21_paper_tracker_skips_post_when_no_new_papers():
    """No HTTP request when pipeline returns no new URLs."""
    with patch(
        "wg21_paper_tracker.collectors.run_tracker_pipeline",
        return_value=TrackerPipelineResult(),
    ):
        with patch(
            "wg21_paper_tracker.collectors.requests.post",
        ) as m_post:
            with override_settings(
                WG21_GITHUB_DISPATCH_ENABLED=True,
                WG21_GITHUB_DISPATCH_REPO="o/r",
                WG21_GITHUB_DISPATCH_TOKEN="t",
            ):
                call_command(RUN_TRACKER_CMD)
    m_post.assert_not_called()


@pytest.mark.django_db
def test_run_wg21_paper_tracker_skips_post_when_dispatch_disabled():
    """No HTTP request when WG21_GITHUB_DISPATCH_ENABLED is False."""
    with patch(
        "wg21_paper_tracker.collectors.run_tracker_pipeline",
        return_value=TrackerPipelineResult(new_paper_urls=("https://x/y",)),
    ):
        with patch(
            "wg21_paper_tracker.collectors.requests.post",
        ) as m_post:
            with override_settings(
                WG21_GITHUB_DISPATCH_ENABLED=False,
                WG21_GITHUB_DISPATCH_REPO="o/r",
                WG21_GITHUB_DISPATCH_TOKEN="t",
            ):
                call_command(RUN_TRACKER_CMD)
    m_post.assert_not_called()


@pytest.mark.django_db
def test_run_wg21_paper_tracker_rejects_invalid_from_date():
    """--from-date must be YYYY-MM."""
    with pytest.raises(CommandError, match="Invalid from_mailing_date"):
        call_command(RUN_TRACKER_CMD, "--from-date=bad")


@pytest.mark.django_db
def test_run_wg21_paper_tracker_passes_from_date_to_pipeline():
    with patch(
        "wg21_paper_tracker.collectors.run_tracker_pipeline",
        return_value=TrackerPipelineResult(),
    ) as m:
        call_command(RUN_TRACKER_CMD, "--from-date=2025-03")
    m.assert_called_once_with(from_mailing_date="2025-03", to_mailing_date=None)


@pytest.mark.django_db
def test_run_wg21_paper_tracker_rejects_invalid_to_date():
    with pytest.raises(CommandError, match="Invalid to_mailing_date"):
        call_command(RUN_TRACKER_CMD, "--to-date=bad")


@pytest.mark.django_db
def test_run_wg21_paper_tracker_passes_from_and_to_date_to_pipeline():
    with patch(
        "wg21_paper_tracker.collectors.run_tracker_pipeline",
        return_value=TrackerPipelineResult(),
    ) as m:
        call_command(RUN_TRACKER_CMD, "--from-date=2025-01", "--to-date=2025-03")
    m.assert_called_once_with(from_mailing_date="2025-01", to_mailing_date="2025-03")
