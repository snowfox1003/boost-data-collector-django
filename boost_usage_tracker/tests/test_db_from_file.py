"""Tests for boost_usage_tracker.db_from_file."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from boost_usage_tracker.db_from_file import (
    _load_all_json_records,
    _load_json_records_from_path,
    _normalize_account_type,
    get_github_account_dir,
    update_db_from_file,
)
from cppa_user_tracker.models import GitHubAccount, GitHubAccountType


def test_get_github_account_dir_returns_path_under_workspace(tmp_path):
    """get_github_account_dir returns .../boost_usage_tracker/github_account."""
    app_dir = tmp_path / "boost_usage_tracker"
    app_dir.mkdir(parents=True)
    with patch("boost_usage_tracker.db_from_file.get_workspace_path") as m:
        m.return_value = app_dir
        path = get_github_account_dir()
    assert path == app_dir / "github_account"
    assert path.is_dir()
    m.assert_called_once_with("boost_usage_tracker")


@pytest.mark.django_db
def test_update_db_from_file_unsupported_table_returns_errors():
    """update_db_from_file returns errors for unsupported table."""
    result = update_db_from_file(table="unknown_table")
    assert result["table"] == "unknown_table"
    assert result["created"] == 0
    assert result["updated"] == 0
    assert "Unsupported table" in result["errors"][0]


@pytest.mark.django_db
def test_update_db_from_file_github_account_from_dir(tmp_path):
    """update_db_from_file loads JSON from dir and creates/updates GitHubAccount and BaseProfile."""
    (tmp_path / "a.json").write_text(
        json.dumps(
            {
                "github_account_id": 1001,
                "username": "alice",
                "display_name": "Alice",
                "account_type": "user",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "b.json").write_text(
        json.dumps(
            [
                {"github_account_id": 1002, "username": "bob", "account_type": "user"},
                {
                    "github_account_id": 1003,
                    "username": "org1",
                    "account_type": "organization",
                },
            ]
        ),
        encoding="utf-8",
    )
    result = update_db_from_file(source=tmp_path, table="github_account")
    assert result["table"] == "github_account"
    assert result["source_path"] == str(tmp_path)
    assert result["created"] == 3
    assert result["updated"] == 0
    assert GitHubAccount.objects.filter(github_account_id=1001).exists()
    assert GitHubAccount.objects.filter(github_account_id=1002).exists()
    assert GitHubAccount.objects.filter(github_account_id=1003).exists()
    acc1 = GitHubAccount.objects.get(github_account_id=1001)
    assert acc1.username == "alice"
    assert acc1.display_name == "Alice"
    acc3 = GitHubAccount.objects.get(github_account_id=1003)
    assert acc3.account_type == "organization"


@pytest.mark.django_db
def test_update_db_from_file_github_account_from_single_json_file(tmp_path):
    """update_db_from_file accepts a single .json file as source."""
    (tmp_path / "single.json").write_text(
        json.dumps({"github_account_id": 2001, "username": "single"}),
        encoding="utf-8",
    )
    result = update_db_from_file(
        source=tmp_path / "single.json", table="github_account"
    )
    assert result["created"] == 1
    assert GitHubAccount.objects.get(github_account_id=2001).username == "single"


@pytest.mark.django_db
def test_update_db_from_file_github_account_skips_invalid_records(tmp_path):
    """Records missing github_account_id or with invalid id are skipped."""
    (tmp_path / "mixed.json").write_text(
        json.dumps(
            [
                {"github_account_id": 3001, "username": "ok"},
                {"username": "no_id"},
                {"github_account_id": "not_a_number", "username": "bad"},
            ]
        ),
        encoding="utf-8",
    )
    result = update_db_from_file(source=tmp_path, table="github_account")
    assert result["created"] == 1
    assert GitHubAccount.objects.filter(github_account_id=3001).exists()


def test_normalize_account_type_variants():
    assert _normalize_account_type(None) == GitHubAccountType.USER
    assert _normalize_account_type("org") == GitHubAccountType.ORGANIZATION
    assert _normalize_account_type("enterprise") == GitHubAccountType.ENTERPRISE
    assert _normalize_account_type("unknown") == GitHubAccountType.USER


def test_load_json_records_skips_dotfile(tmp_path):
    p = tmp_path / ".secret.json"
    p.write_text('{"github_account_id": 1}', encoding="utf-8")
    assert _load_json_records_from_path(p) == []


def test_load_json_records_non_dict_list_returns_empty(tmp_path):
    p = tmp_path / "bad_shape.json"
    p.write_text('"scalar"', encoding="utf-8")
    assert _load_json_records_from_path(p) == []


@pytest.mark.django_db
def test_update_db_from_file_invalid_source_path(tmp_path):
    bad = tmp_path / "not_json.txt"
    bad.write_text("x", encoding="utf-8")
    result = update_db_from_file(source=bad, table="github_account")
    assert result["created"] == 0
    assert "not a directory or a .json file" in result["errors"][0].lower()


def test_load_all_json_records_missing_dir_logs(caplog):
    import logging

    caplog.set_level(logging.WARNING)
    assert _load_all_json_records(Path("/nonexistent/path/xyz")) == []
    assert any("does not exist" in r.message for r in caplog.records)


def test_load_all_json_records_skips_bad_json(tmp_path, caplog):
    import logging

    caplog.set_level(logging.WARNING)
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    assert _load_all_json_records(tmp_path) == []
    assert any("Skipping" in r.message for r in caplog.records)


@pytest.mark.django_db
def test_update_db_from_file_skips_non_dict_record(tmp_path, caplog):
    import logging

    caplog.set_level(logging.WARNING)
    (tmp_path / "mix.json").write_text(
        json.dumps([{"github_account_id": 4001}, "skip"]), encoding="utf-8"
    )
    result = update_db_from_file(source=tmp_path, table="github_account")
    assert result["created"] == 1
    assert GitHubAccount.objects.filter(github_account_id=4001).exists()


@pytest.mark.django_db
def test_update_db_from_file_updates_existing_account(tmp_path):
    (tmp_path / "one.json").write_text(
        json.dumps({"github_account_id": 5001, "username": "first"}),
        encoding="utf-8",
    )
    r1 = update_db_from_file(source=tmp_path, table="github_account")
    assert r1["created"] == 1 and r1["updated"] == 0
    (tmp_path / "one.json").write_text(
        json.dumps({"github_account_id": 5001, "username": "second"}),
        encoding="utf-8",
    )
    r2 = update_db_from_file(source=tmp_path, table="github_account")
    assert r2["updated"] >= 1
    assert GitHubAccount.objects.get(github_account_id=5001).username == "second"


@pytest.mark.django_db
def test_update_db_from_file_recursive_subdir(tmp_path):
    sub = tmp_path / "nested"
    sub.mkdir()
    (sub / "deep.json").write_text(
        json.dumps({"github_account_id": 6001, "username": "deep"}),
        encoding="utf-8",
    )
    result = update_db_from_file(source=tmp_path, table="github_account")
    assert result["created"] == 1
    assert GitHubAccount.objects.filter(github_account_id=6001).exists()
