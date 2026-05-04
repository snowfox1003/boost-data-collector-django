"""Tests for cleanup_workspace_orphans management command."""

import os
import time
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_cleanup_workspace_orphans_dry_run_reports_candidates(tmp_path):
    stale = tmp_path / "orphan.tmp"
    stale.write_text("x", encoding="utf-8")
    old = time.time() - 48 * 3600
    os.utime(stale, (old, old))

    with patch("django.conf.settings.WORKSPACE_DIR", tmp_path):
        out = StringIO()
        call_command("cleanup_workspace_orphans", stdout=out)
    text = out.getvalue()
    assert "would delete" in text or "Found" in text


@pytest.mark.django_db
def test_cleanup_workspace_orphans_execute_removes_file(tmp_path):
    stale = tmp_path / "gone.lock"
    stale.write_text("lock", encoding="utf-8")
    old = time.time() - 48 * 3600
    os.utime(stale, (old, old))

    with patch("django.conf.settings.WORKSPACE_DIR", tmp_path):
        out = StringIO()
        call_command(
            "cleanup_workspace_orphans",
            "--execute",
            stdout=out,
        )
    assert not stale.exists()


@pytest.mark.django_db
def test_cleanup_workspace_orphans_errors_when_workspace_not_dir(tmp_path):
    not_dir = tmp_path / "file_not_dir"
    not_dir.write_text("x", encoding="utf-8")
    err = StringIO()
    out = StringIO()
    with patch("django.conf.settings.WORKSPACE_DIR", not_dir):
        call_command(
            "cleanup_workspace_orphans",
            stdout=out,
            stderr=err,
        )
    assert "not a directory" in err.getvalue().lower()


@pytest.mark.django_db
def test_cleanup_workspace_orphans_skips_non_matching_suffix(tmp_path):
    stale = tmp_path / "readme.txt"
    stale.write_text("x", encoding="utf-8")
    old = time.time() - 48 * 3600
    os.utime(stale, (old, old))
    out = StringIO()
    with patch("django.conf.settings.WORKSPACE_DIR", tmp_path):
        call_command("cleanup_workspace_orphans", stdout=out)
    assert "readme.txt" not in out.getvalue()


@pytest.mark.django_db
def test_cleanup_workspace_orphans_skips_recent_files(tmp_path):
    fresh = tmp_path / "fresh.tmp"
    fresh.write_text("x", encoding="utf-8")
    out = StringIO()
    with patch("django.conf.settings.WORKSPACE_DIR", tmp_path):
        call_command(
            "cleanup_workspace_orphans",
            "--max-age-hours",
            "24",
            stdout=out,
        )
    assert "fresh.tmp" not in out.getvalue()


@pytest.mark.django_db
def test_cleanup_workspace_orphans_includes_nested_orphan(tmp_path):
    nested = tmp_path / "sub" / "deep.swp"
    nested.parent.mkdir(parents=True)
    nested.write_text("", encoding="utf-8")
    old = time.time() - 48 * 3600
    os.utime(nested, (old, old))
    out = StringIO()
    with patch("django.conf.settings.WORKSPACE_DIR", tmp_path):
        call_command("cleanup_workspace_orphans", stdout=out)
    assert "deep.swp" in out.getvalue()


@pytest.mark.django_db
def test_cleanup_workspace_orphans_execute_logs_when_unlink_fails(tmp_path):
    stale = tmp_path / "locked.part"
    stale.write_text("x", encoding="utf-8")
    old = time.time() - 48 * 3600
    os.utime(stale, (old, old))
    out = StringIO()
    err = StringIO()
    with patch("django.conf.settings.WORKSPACE_DIR", tmp_path):
        with patch.object(Path, "unlink", side_effect=OSError("permission")):
            call_command(
                "cleanup_workspace_orphans",
                "--execute",
                stdout=out,
                stderr=err,
            )
    lower = err.getvalue().lower()
    assert "skip" in lower or "permission" in lower
