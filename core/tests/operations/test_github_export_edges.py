"""Extra branch coverage for github_export helpers."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.operations.md_ops import github_export as ge


def test_detect_renames_skips_blob_with_empty_path():
    tree = [
        {"type": "blob", "path": ""},
        {"type": "tree", "path": "issues/2024/2024-01"},
    ]
    new_files = {"issues/2024/2024-01/#1 - New.md": "/x"}
    assert ge.detect_renames(tree, new_files) == []


def test_detect_stale_titled_paths_skips_dot_git_and_dotfiles(tmp_path: Path):
    month = tmp_path / "issues" / "2024" / "2024-03"
    month.mkdir(parents=True)
    (month / "#1 - Old.md").write_text("x", encoding="utf-8")
    (month / ".hidden.md").write_text("x", encoding="utf-8")
    gitdir = month / ".git"
    gitdir.mkdir()
    (gitdir / "config").write_text("[core]\n", encoding="utf-8")
    new_files = {"issues/2024/2024-03/#1 - New.md": str(month / "#1 - New.md")}
    stale = ge.detect_stale_titled_paths(tmp_path, new_files)
    assert stale == ["issues/2024/2024-03/#1 - Old.md"]


def test_parse_dt_non_string_returns_none():
    assert ge._parse_dt(None) is None
    assert ge._parse_dt(123) is None


def test_md_path_converts_timezone_aware_created_at_to_utc_date_parts(tmp_path: Path):
    dt = datetime(2024, 6, 30, 21, 0, tzinfo=timezone(timedelta(hours=-5)))
    p = ge._md_path(tmp_path, "", "issues", dt, 3, "Title")
    rel = p.relative_to(tmp_path).as_posix()
    assert "2024-07" in rel
