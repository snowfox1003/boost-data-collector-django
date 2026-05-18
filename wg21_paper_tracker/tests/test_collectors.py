"""Tests for WG21 collector helpers (repository_dispatch + AbstractCollector impl)."""

import logging
from unittest.mock import MagicMock, patch

import pytest
import requests
from django.core.management.base import CommandError

from wg21_paper_tracker.collectors import (
    Wg21PaperTrackerCollector,
    trigger_github_repository_dispatch,
)
from wg21_paper_tracker.pipeline import TrackerPipelineResult


def test_trigger_github_repository_dispatch_raises_on_http_error():
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 422
    mock_resp.text = "validation failed"
    mock_resp.raise_for_status.side_effect = requests.HTTPError("422")

    with patch(
        "wg21_paper_tracker.collectors.requests.post",
        return_value=mock_resp,
    ):
        with pytest.raises(requests.HTTPError):
            trigger_github_repository_dispatch(
                "org/repo",
                "paper_event",
                "tok",
                ["https://example.com/a.pdf"],
            )


@pytest.mark.parametrize(
    ("dry_run", "from_date", "to_date", "expect_dates_in_message"),
    [
        (True, None, None, False),
        (True, "2025-01", None, True),
        (True, "2025-01", "2025-03", True),
    ],
)
def test_wg21_collector_dry_run_short_circuits(
    caplog,
    dry_run,
    from_date,
    to_date,
    expect_dates_in_message,
):
    caplog.set_level(logging.INFO)
    collector = Wg21PaperTrackerCollector(
        dry_run=dry_run,
        from_date=from_date,
        to_date=to_date,
    )
    with patch(
        "wg21_paper_tracker.collectors.run_tracker_pipeline",
    ) as m_pipeline:
        collector.run()
    m_pipeline.assert_not_called()
    joined = " ".join(r.message for r in caplog.records)
    assert "Dry run" in joined
    if expect_dates_in_message:
        assert "from=" in joined


def test_wg21_collector_valueerror_maps_to_command_error():
    collector = Wg21PaperTrackerCollector(
        dry_run=False,
        from_date=None,
        to_date=None,
    )
    with patch(
        "wg21_paper_tracker.collectors.run_tracker_pipeline",
        side_effect=ValueError("bad window"),
    ):
        with pytest.raises(CommandError, match="bad window"):
            collector.run()


def test_wg21_collector_propagates_non_valueerror_exceptions():
    collector = Wg21PaperTrackerCollector(
        dry_run=False,
        from_date=None,
        to_date=None,
    )
    with patch(
        "wg21_paper_tracker.collectors.run_tracker_pipeline",
        side_effect=RuntimeError("boom"),
    ):
        with pytest.raises(RuntimeError, match="boom"):
            collector.run()


@pytest.mark.django_db
def test_wg21_collector_dispatch_http_error_is_logged_and_raised():
    from django.test.utils import override_settings

    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 500
    mock_resp.text = "error"
    mock_resp.raise_for_status.side_effect = requests.HTTPError("500")

    collector = Wg21PaperTrackerCollector(
        dry_run=False,
        from_date=None,
        to_date=None,
    )
    with override_settings(
        WG21_GITHUB_DISPATCH_ENABLED=True,
        WG21_GITHUB_DISPATCH_REPO="o/r",
        WG21_GITHUB_DISPATCH_TOKEN="secret",
    ):
        with patch(
            "wg21_paper_tracker.collectors.run_tracker_pipeline",
            return_value=TrackerPipelineResult(
                new_paper_urls=("https://papers.example/p.pdf",),
            ),
        ):
            with patch(
                "wg21_paper_tracker.collectors.requests.post",
                return_value=mock_resp,
            ):
                with pytest.raises(requests.HTTPError):
                    collector.run()
