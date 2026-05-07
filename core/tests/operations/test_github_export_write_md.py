"""Tests for core.operations.md_ops.github_export.write_md_files and helpers."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.operations.md_ops.github_export import write_md_files


def _minimal_issue(number: int = 7) -> dict:
    return {
        "issue_info": {
            "number": number,
            "title": 'Unsafe /:*?"<>|chars',
            "state": "open",
            "user": {"login": "alice"},
            "created_at": "2024-02-10T08:00:00Z",
            "updated_at": "2024-02-10T09:00:00Z",
            "html_url": f"https://github.com/o/r/issues/{number}",
            "body": "Body.",
        },
        "comments": [],
    }


def _minimal_pr(number: int = 3) -> dict:
    return {
        "pr_info": {
            "number": number,
            "title": "PR title",
            "state": "open",
            "user": {"login": "bob"},
            "created_at": "2024-02-11T12:00:00+00:00",
            "updated_at": "2024-02-11T12:00:00+00:00",
            "html_url": f"https://github.com/o/r/pull/{number}",
            "body": "PR body.",
        },
        "comments": [],
    }


@patch("core.operations.md_ops.github_export.get_raw_source_issue_path")
@patch("core.operations.md_ops.github_export.get_raw_source_pr_path")
def test_write_md_files_writes_issue_and_pr(
    mock_pr_path, mock_issue_path, tmp_path: Path
):
    issue_file = tmp_path / "raw_issue.json"
    pr_file = tmp_path / "raw_pr.json"
    issue_file.write_text(json.dumps(_minimal_issue(7)), encoding="utf-8")
    pr_file.write_text(json.dumps(_minimal_pr(3)), encoding="utf-8")
    mock_issue_path.return_value = issue_file
    mock_pr_path.return_value = pr_file

    out_root = tmp_path / "export"
    out_root.mkdir()
    mapping = write_md_files(
        "owner",
        "repo",
        issue_numbers=[7],
        pr_numbers=[3],
        output_dir=out_root,
        folder_prefix="boost",
    )
    assert len(mapping) == 2
    issue_md = (
        out_root / "boost" / "issues" / "2024" / "2024-02" / "#7 - Unsafe chars.md"
    )
    pr_md = (
        out_root / "boost" / "pull_requests" / "2024" / "2024-02" / "#3 - PR title.md"
    )
    assert issue_md.is_file()
    assert pr_md.is_file()
    body = issue_md.read_text(encoding="utf-8")
    assert "# #7 -" in body
    assert "Body." in body


@patch("core.operations.md_ops.github_export.get_raw_source_issue_path")
def test_write_md_files_skips_missing_raw(mock_issue_path, tmp_path: Path):
    missing = tmp_path / "nope.json"
    mock_issue_path.return_value = missing
    out_root = tmp_path / "out"
    out_root.mkdir()
    assert write_md_files("o", "r", [99], [], out_root) == {}


@patch("core.operations.md_ops.github_export.get_raw_source_issue_path")
def test_write_md_files_skips_invalid_json(mock_issue_path, tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    mock_issue_path.return_value = bad
    out_root = tmp_path / "out2"
    out_root.mkdir()
    assert write_md_files("o", "r", [1], [], out_root) == {}


@patch("core.operations.md_ops.github_export.get_raw_source_issue_path")
def test_write_md_files_uses_fallback_title_and_naive_created_at(
    mock_issue_path, tmp_path: Path
):
    data = {
        "issue_info": {
            "number": 5,
            "title": "",
            "state": "open",
            "user": {"login": "u"},
            "created_at": "not-iso",
            "body": "",
        },
        "comments": [],
    }
    f = tmp_path / "i.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    mock_issue_path.return_value = f
    out_root = tmp_path / "out3"
    out_root.mkdir()
    write_md_files("o", "r", [5], [], out_root, folder_prefix="")
    written = list(out_root.rglob("*.md"))
    assert len(written) == 1
    assert "issue-5" in written[0].name


@patch("core.operations.md_ops.github_export.get_raw_source_issue_path")
def test_write_md_files_write_failure_logged(mock_issue_path, tmp_path: Path):
    data = _minimal_issue(2)
    f = tmp_path / "ok.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    mock_issue_path.return_value = f
    out_root = tmp_path / "out4"
    out_root.mkdir()

    def boom(*_a, **_k):
        raise OSError("disk full")

    with patch.object(Path, "write_text", side_effect=boom):
        assert write_md_files("o", "r", [2], [], out_root) == {}


@patch("core.operations.md_ops.github_export.get_raw_source_pr_path")
def test_write_md_files_pr_write_failure(mock_pr_path, tmp_path: Path):
    data = {
        "pr_info": {
            "number": 9,
            "title": "PR",
            "state": "open",
            "user": {"login": "u"},
            "created_at": "2024-02-11T12:00:00Z",
            "body": "",
        },
        "comments": [],
    }
    f = tmp_path / "pr.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    mock_pr_path.return_value = f
    out_root = tmp_path / "out5"
    out_root.mkdir()

    def boom(*_a, **_k):
        raise OSError("write fail")

    with patch.object(Path, "write_text", side_effect=boom):
        assert write_md_files("o", "r", [], [9], out_root) == {}


@patch("core.operations.md_ops.github_export.get_raw_source_pr_path")
def test_write_md_files_skips_pr_when_raw_json_missing(mock_pr_path, tmp_path: Path):
    raw = MagicMock()
    raw.exists.return_value = False
    mock_pr_path.return_value = raw
    out_root = tmp_path / "out_missing_pr"
    out_root.mkdir()
    assert write_md_files("ow", "rp", [], [3], out_root) == {}


@patch("core.operations.md_ops.github_export.get_raw_source_pr_path")
def test_write_md_files_skips_pr_when_json_invalid(mock_pr_path, tmp_path: Path):
    f = tmp_path / "bad_pr.json"
    f.write_text("{", encoding="utf-8")
    mock_pr_path.return_value = f
    out_root = tmp_path / "out_bad_pr"
    out_root.mkdir()
    assert write_md_files("ow", "rp", [], [3], out_root) == {}
