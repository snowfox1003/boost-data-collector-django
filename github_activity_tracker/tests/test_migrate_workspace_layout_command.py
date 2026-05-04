"""Tests for migrate_workspace_layout management command."""

from io import StringIO

import pytest
from django.conf import settings
from django.core.management import call_command


@pytest.fixture
def legacy_github_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "WORKSPACE_DIR", str(tmp_path))
    root = tmp_path / "github_activity_tracker"
    owner = root / "boostorg"
    commits = owner / "commits" / "boost" / "master"
    commits.mkdir(parents=True)
    (commits / "deadbeef.json").write_text("{}", encoding="utf-8")

    issues = owner / "issues" / "boost"
    issues.mkdir(parents=True)
    (issues / "issue_42.json").write_text("{}", encoding="utf-8")

    prs = owner / "prs" / "boost"
    prs.mkdir(parents=True)
    (prs / "pr_7.json").write_text("{}", encoding="utf-8")

    return root


def test_migrate_workspace_warns_when_root_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "WORKSPACE_DIR", str(tmp_path))
    out = StringIO()
    call_command("migrate_workspace_layout", stdout=out, verbosity=0)
    assert "does not exist" in out.getvalue()


def test_migrate_workspace_dry_run_lists_moves(legacy_github_workspace):
    out = StringIO()
    call_command(
        "migrate_workspace_layout",
        dry_run=True,
        stdout=out,
        verbosity=0,
    )
    text = out.getvalue()
    assert "would move" in text.lower()
    assert "Dry run" in text


def test_migrate_workspace_moves_files(legacy_github_workspace):
    out = StringIO()
    call_command("migrate_workspace_layout", stdout=out, verbosity=0)
    owner = legacy_github_workspace / "boostorg"
    assert (owner / "boost" / "commits" / "deadbeef.json").is_file()
    assert (owner / "boost" / "issues" / "42.json").is_file()
    assert (owner / "boost" / "prs" / "7.json").is_file()
    assert "Moved" in out.getvalue()
