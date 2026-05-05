"""Tests for CSV/git-account update helpers."""

import json

import pytest

from boost_usage_tracker.update_boostusage_from_csv import (
    update_boostusage_table_from_csv,
)
from boost_usage_tracker.update_githubfile_from_csv import (
    update_githubfile_table_from_csv,
)
from boost_usage_tracker.update_git_account import update_git_account
from boost_usage_tracker.update_repository_from_csv import (
    update_repository_table_from_csv,
)
from boost_usage_tracker.models import BoostUsage


@pytest.mark.django_db
def test_update_githubfile_table_from_csv_creates(tmp_path, github_account):
    from model_bakery import baker

    repo = baker.make(
        "github_activity_tracker.GitHubRepository",
        owner_account=github_account,
        repo_name="usage-csv-repo",
    )
    csv_path = tmp_path / "gf.csv"
    csv_path.write_text(
        "owner,repo_name,file_path,is_deleted\n"
        f"{github_account.username},{repo.repo_name},src/a.cpp,false\n",
        encoding="utf-8",
    )
    result = update_githubfile_table_from_csv(csv_path)
    assert result["created"] == 1
    assert result["skipped_no_repo"] == 0


@pytest.mark.django_db
def test_update_githubfile_missing_file_and_bad_columns(tmp_path):
    r = update_githubfile_table_from_csv(tmp_path / "missing.csv")
    assert "not found" in r["errors"][0].lower()

    bad = tmp_path / "badcols.csv"
    bad.write_text("a,b\n1,2\n", encoding="utf-8")
    r2 = update_githubfile_table_from_csv(bad)
    assert any("owner" in e for e in r2["errors"])


@pytest.mark.django_db
def test_update_repository_table_from_csv(tmp_path, github_account):
    import uuid

    repo_slug = "new-ext-" + uuid.uuid4().hex[:8]
    csv_path = tmp_path / "repo.csv"
    csv_path.write_text(
        "owner,repo_name,stars,forks,boost_version,is_boost_embedded,is_boost_used\n"
        f"{github_account.username},{repo_slug},5,1,1.83,false,true\n",
        encoding="utf-8",
    )
    result = update_repository_table_from_csv(csv_path)
    assert result["created_repos"] == 1
    assert result["created_ext"] == 1


@pytest.mark.django_db
def test_update_repository_skips_unknown_owner(tmp_path):
    csv_path = tmp_path / "repo.csv"
    csv_path.write_text(
        "owner,repo_name\nunknown_owner_xyz,whatever\n", encoding="utf-8"
    )
    result = update_repository_table_from_csv(csv_path)
    assert result["skipped_no_owner"] == 1


@pytest.mark.django_db
def test_update_boostusage_table_from_csv_and_except(
    tmp_path, ext_repo, external_github_file, boost_file
):
    owner = ext_repo.owner_account.username
    header_fn = boost_file.github_file.filename
    csv_path = tmp_path / "bu.csv"
    csv_path.write_text(
        "owner,repo_name,file_path,boost_header_name,last_commit_ts,excepted_at\n"
        f"{owner},{ext_repo.repo_name},{external_github_file.filename},"
        f"{header_fn},2024-06-01T12:00:00Z,yes\n",
        encoding="utf-8",
    )
    result = update_boostusage_table_from_csv(csv_path)
    assert result["created"] == 1 or result["updated"] == 1
    usage = BoostUsage.objects.filter(repo=ext_repo).first()
    assert usage is not None
    assert usage.excepted_at is not None


@pytest.mark.django_db
def test_update_git_account_with_owner_wrapped_json(tmp_path):
    (tmp_path / "acc.json").write_text(
        json.dumps(
            {
                "owner": {
                    "id": 88001001,
                    "login": "wrapped-user",
                    "name": "Wrapped",
                    "avatar_url": "",
                    "type": "User",
                }
            }
        ),
        encoding="utf-8",
    )
    result = update_git_account(source=tmp_path / "acc.json", table="github_account")
    assert result["created"] + result["updated"] >= 1


@pytest.mark.django_db
def test_update_git_account_unsupported_table():
    result = update_git_account(table="other")
    assert any("Unsupported" in e for e in result["errors"])
