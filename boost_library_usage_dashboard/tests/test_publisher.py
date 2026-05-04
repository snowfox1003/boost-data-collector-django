"""Tests for boost_library_usage_dashboard.publisher validation."""

from unittest.mock import patch

import pytest
from django.conf import settings
from django.core.management.base import CommandError

from boost_library_usage_dashboard.publisher import publish_dashboard


def _fake_clone(_slug, dest, token=None):
    dest.mkdir(parents=True, exist_ok=True)
    (dest / ".git").mkdir()


@pytest.mark.django_db
def test_publish_dashboard_full_flow_mocked_git(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    (out / "index.html").write_text("<html/>", encoding="utf-8")
    with patch.object(settings, "RAW_DIR", str(raw)):
        with patch(
            "boost_library_usage_dashboard.publisher.clone_repo",
            side_effect=_fake_clone,
        ):
            with patch(
                "boost_library_usage_dashboard.publisher.prepare_repo_for_pull",
            ):
                with patch("boost_library_usage_dashboard.publisher.pull"):
                    with patch("boost_library_usage_dashboard.publisher.push"):
                        publish_dashboard(out, "org", "repo", "main")


@pytest.mark.django_db
def test_publish_dashboard_rejects_owner_with_path_separator(tmp_path):
    """Owner must be a single slug; path separators are rejected."""
    raw = tmp_path / "raw"
    raw.mkdir()
    with patch.object(settings, "RAW_DIR", str(raw)):
        with pytest.raises(CommandError, match="Invalid GitHub owner"):
            publish_dashboard(
                tmp_path / "out",
                owner="foo/bar",
                repo="repo",
                branch="main",
            )


@pytest.mark.django_db
def test_publish_dashboard_rejects_dotdot_repo(tmp_path):
    """Repo must not be path-like."""
    raw = tmp_path / "raw"
    raw.mkdir()
    with patch.object(settings, "RAW_DIR", str(raw)):
        with pytest.raises(CommandError, match="Invalid GitHub repo"):
            publish_dashboard(
                tmp_path / "out",
                owner="org",
                repo="..",
                branch="main",
            )


@pytest.mark.django_db
def test_publish_dashboard_rejects_invalid_slug_chars(tmp_path):
    """Spaces and other disallowed characters are rejected."""
    raw = tmp_path / "raw"
    raw.mkdir()
    with patch.object(settings, "RAW_DIR", str(raw)):
        with pytest.raises(CommandError, match="Invalid GitHub owner"):
            publish_dashboard(
                tmp_path / "out",
                owner="bad name",
                repo="repo",
                branch="main",
            )
