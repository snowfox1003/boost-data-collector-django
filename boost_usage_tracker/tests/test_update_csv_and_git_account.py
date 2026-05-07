"""Tests for CSV/git-account update helpers."""

import json
import logging
from unittest.mock import patch

import pytest

from cppa_user_tracker.models import GitHubAccount, GitHubAccountType

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


@pytest.mark.django_db
def test_update_git_account_rejects_non_json_source(tmp_path):
    p = tmp_path / "data.txt"
    p.write_text("nope", encoding="utf-8")
    r = update_git_account(source=p, table="github_account")
    assert "not a directory or .json file" in r["errors"][0].lower()


@pytest.mark.django_db
def test_update_git_account_single_file_json_error(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    r = update_git_account(source=bad, table="github_account")
    assert r["created"] == 0
    assert any("skipping" in e.lower() for e in r["errors"])


@pytest.mark.django_db
def test_update_git_account_nonexistent_path_is_not_dir_nor_file(tmp_path):
    missing = tmp_path / "nope" / "dir"
    r = update_git_account(source=missing, table="github_account")
    assert "not a directory or .json file" in r["errors"][0].lower()


@pytest.mark.django_db
def test_update_git_account_dir_loads_org_and_enterprise_types(tmp_path):
    (tmp_path / "accounts.json").write_text(
        json.dumps(
            [
                {
                    "owner": {
                        "id": 91001102,
                        "login": "org-acct",
                        "type": "Organization",
                    }
                },
                {
                    "owner": {
                        "id": 91001103,
                        "login": "ent-acct",
                        "type": "enterprise",
                    }
                },
            ]
        ),
        encoding="utf-8",
    )
    r = update_git_account(source=tmp_path, table="github_account")
    assert r["created"] + r["updated"] == 2
    assert (
        GitHubAccount.objects.get(github_account_id=91001102).account_type
        == GitHubAccountType.ORGANIZATION
    )
    assert (
        GitHubAccount.objects.get(github_account_id=91001103).account_type
        == GitHubAccountType.ENTERPRISE
    )


@pytest.mark.django_db
def test_update_git_account_skips_bad_records(caplog, tmp_path):
    caplog.set_level(logging.WARNING)
    (tmp_path / "mix.json").write_text(
        json.dumps(
            [
                "not-a-dict",
                {"owner": "bad"},
                {"owner": {"login": "x"}},
                {"owner": {"id": "nan", "login": "y"}},
            ]
        ),
        encoding="utf-8",
    )
    r = update_git_account(source=tmp_path, table="github_account")
    assert r["created"] == 0
    assert sum(1 for rec in caplog.records if "Skipping" in rec.message) >= 3


@pytest.mark.django_db
def test_update_git_account_empty_username_warns(caplog, tmp_path):
    caplog.set_level(logging.WARNING)
    (tmp_path / "e.json").write_text(
        json.dumps({"owner": {"id": 92002002, "login": ""}}),
        encoding="utf-8",
    )
    r = update_git_account(source=tmp_path, table="github_account")
    assert r["created"] + r["updated"] >= 1
    assert any("empty username" in rec.message for rec in caplog.records)


@pytest.mark.django_db
def test_update_git_account_directory_skips_bad_json(tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    (tmp_path / "bad.json").write_text("{", encoding="utf-8")
    (tmp_path / "ok.json").write_text(
        json.dumps({"owner": {"id": 92002003, "login": "goodjson"}}),
        encoding="utf-8",
    )
    r = update_git_account(source=tmp_path, table="github_account")
    assert r["created"] + r["updated"] >= 1
    assert any("Skipping" in rec.message for rec in caplog.records)


@pytest.mark.django_db
def test_update_boostusage_csv_not_found(tmp_path):
    r = update_boostusage_table_from_csv(tmp_path / "nope.csv")
    assert "not found" in r["errors"][0].lower()


@pytest.mark.django_db
def test_update_boostusage_csv_bad_columns(tmp_path):
    p = tmp_path / "bu.csv"
    p.write_text("a,b\n1,2\n", encoding="utf-8")
    r = update_boostusage_table_from_csv(p)
    assert any("csv must have columns" in e.lower() for e in r["errors"])


@pytest.mark.django_db
def test_update_boostusage_skipped_counters(tmp_path, github_account, ext_repo):
    """skipped_no_repo / skipped_no_file / skipped_no_boost_header."""
    owner = github_account.username
    p = tmp_path / "bu.csv"
    p.write_text(
        "owner,repo_name,file_path,boost_header_name\n"
        f"{owner},nonexistent-repo,x.cpp,h.hpp\n"
        f"{owner},{ext_repo.repo_name},missing.cpp,h.hpp\n"
        f"{owner},{ext_repo.repo_name},src/main.cpp,missing_header.hpp\n",
        encoding="utf-8",
    )
    from model_bakery import baker

    baker.make(
        "github_activity_tracker.GitHubFile",
        repo=ext_repo,
        filename="src/main.cpp",
    )
    r = update_boostusage_table_from_csv(p)
    assert r["skipped_no_repo"] >= 1
    assert r["skipped_no_file"] >= 1
    assert r["skipped_no_boost_header"] >= 1


@pytest.mark.django_db
def test_update_boostusage_open_os_error(tmp_path):
    p = tmp_path / "bu.csv"
    p.write_text(
        "owner,repo_name,file_path,boost_header_name\nx,y,z,h\n", encoding="utf-8"
    )
    with patch(
        "boost_usage_tracker.update_boostusage_from_csv.Path.open",
        side_effect=OSError("disk"),
    ):
        r = update_boostusage_table_from_csv(p)
    assert any("disk" in e.lower() for e in r["errors"])


@pytest.mark.django_db
def test_update_repository_csv_not_found(tmp_path):
    r = update_repository_table_from_csv(tmp_path / "missing.csv")
    assert "not found" in r["errors"][0].lower()


@pytest.mark.django_db
def test_update_repository_csv_bad_columns(tmp_path):
    p = tmp_path / "r.csv"
    p.write_text("only_one_col\nx\n", encoding="utf-8")
    r = update_repository_table_from_csv(p)
    assert any("owner" in e.lower() for e in r["errors"])


@pytest.mark.django_db
def test_update_repository_skips_blank_identifiers(tmp_path, github_account):
    p = tmp_path / "r.csv"
    p.write_text(
        "owner,repo_name\n"
        f",{github_account.username}\n"
        f"{github_account.username},\n",
        encoding="utf-8",
    )
    r = update_repository_table_from_csv(p)
    assert r["created_repos"] == 0


@pytest.mark.django_db
def test_update_repository_invalid_int_stars_defaults(tmp_path, github_account):
    import uuid

    slug = "stars-parse-" + uuid.uuid4().hex[:8]
    p = tmp_path / "r.csv"
    p.write_text(
        "owner,repo_name,stars,forks\n"
        f'{github_account.username},{slug},"not-a-number","bogus"\n',
        encoding="utf-8",
    )
    r = update_repository_table_from_csv(p)
    assert r["created_repos"] == 1
    from github_activity_tracker.models import GitHubRepository

    repo = GitHubRepository.objects.get(owner_account=github_account, repo_name=slug)
    assert repo.stars == 0
    assert repo.forks == 0


@pytest.mark.django_db
def test_update_repository_open_os_error(tmp_path):
    p = tmp_path / "r.csv"
    p.write_text("owner,repo_name\na,b\n", encoding="utf-8")
    with patch(
        "boost_usage_tracker.update_repository_from_csv.Path.open",
        side_effect=OSError("read"),
    ):
        r = update_repository_table_from_csv(p)
    assert any("read" in e.lower() for e in r["errors"])


@pytest.mark.django_db
def test_update_githubfile_csv_not_found(tmp_path):
    r = update_githubfile_table_from_csv(tmp_path / "gf.csv")
    assert "not found" in r["errors"][0].lower()


@pytest.mark.django_db
def test_update_githubfile_bad_columns(tmp_path):
    p = tmp_path / "gf.csv"
    p.write_text("owner,repo_name\nx,y\n", encoding="utf-8")
    r = update_githubfile_table_from_csv(p)
    assert any("file_path" in e.lower() for e in r["errors"])


@pytest.mark.django_db
def test_update_githubfile_skipped_no_repo(tmp_path, github_account):
    p = tmp_path / "gf.csv"
    p.write_text(
        "owner,repo_name,file_path\n"
        f"{github_account.username},ghost-repo,main.cpp\n",
        encoding="utf-8",
    )
    r = update_githubfile_table_from_csv(p)
    assert r["skipped_no_repo"] == 1


@pytest.mark.django_db
def test_update_githubfile_deleted_flag_and_update(tmp_path, github_account):
    from model_bakery import baker

    repo = baker.make(
        "github_activity_tracker.GitHubRepository",
        owner_account=github_account,
        repo_name="gf-flag-repo",
    )
    p = tmp_path / "gf.csv"
    p.write_text(
        "owner,repo_name,file_path,is_deleted\n"
        f"{github_account.username},{repo.repo_name},a.cpp,false\n",
        encoding="utf-8",
    )
    r1 = update_githubfile_table_from_csv(p)
    assert r1["created"] == 1
    p.write_text(
        "owner,repo_name,file_path,is_deleted\n"
        f"{github_account.username},{repo.repo_name},a.cpp,true\n",
        encoding="utf-8",
    )
    r2 = update_githubfile_table_from_csv(p)
    assert r2["updated"] == 1
    from github_activity_tracker.models import GitHubFile

    gf = GitHubFile.objects.get(repo=repo, filename="a.cpp")
    assert gf.is_deleted is True


@pytest.mark.django_db
def test_update_git_account_defaults_to_github_account_dir(tmp_path):
    (tmp_path / "acc.json").write_text(
        json.dumps({"owner": {"id": 92008888, "login": "default-dir-user"}}),
        encoding="utf-8",
    )
    with patch(
        "boost_usage_tracker.update_git_account.get_github_account_dir",
        return_value=tmp_path,
    ):
        result = update_git_account(source=None, table="github_account")
    assert result["created"] + result["updated"] >= 1
    assert GitHubAccount.objects.filter(github_account_id=92008888).exists()


@pytest.mark.django_db
def test_update_repository_optional_datetime_columns(tmp_path, github_account):
    import uuid

    slug = "dt-repo-" + uuid.uuid4().hex[:8]
    ts = "2024-02-01T12:00:00Z"
    p = tmp_path / "r.csv"
    p.write_text(
        "owner,repo_name,repo_pushed_at,repo_created_at,repo_updated_at\n"
        f"{github_account.username},{slug},{ts},{ts},{ts}\n",
        encoding="utf-8",
    )
    result = update_repository_table_from_csv(p)
    assert result["created_repos"] == 1


@pytest.mark.django_db
def test_update_repository_whitespace_description_skipped(tmp_path, github_account):
    import uuid

    slug = "nodesc-" + uuid.uuid4().hex[:8]
    p = tmp_path / "r.csv"
    p.write_text(
        "owner,repo_name,description\n" f"{github_account.username},{slug},   \n",
        encoding="utf-8",
    )
    update_repository_table_from_csv(p)
    from github_activity_tracker.models import GitHubRepository

    repo = GitHubRepository.objects.get(owner_account=github_account, repo_name=slug)
    assert repo.description == ""


@pytest.mark.django_db
def test_update_boostusage_blank_last_commit_ts(
    tmp_path, ext_repo, external_github_file, boost_file
):
    owner = ext_repo.owner_account.username
    header_fn = boost_file.github_file.filename
    p = tmp_path / "bu.csv"
    p.write_text(
        "owner,repo_name,file_path,boost_header_name,last_commit_ts\n"
        f"{owner},{ext_repo.repo_name},{external_github_file.filename},"
        f"{header_fn},\n",
        encoding="utf-8",
    )
    result = update_boostusage_table_from_csv(p)
    assert result["created"] == 1 or result["updated"] == 1


@pytest.mark.django_db
def test_update_boostusage_updates_existing_row(
    tmp_path, ext_repo, external_github_file, boost_file
):
    owner = ext_repo.owner_account.username
    header_fn = boost_file.github_file.filename
    p = tmp_path / "bu.csv"
    body = (
        "owner,repo_name,file_path,boost_header_name,last_commit_ts\n"
        f"{owner},{ext_repo.repo_name},{external_github_file.filename},"
        f"{header_fn},2024-01-01T00:00:00Z\n"
    )
    p.write_text(body, encoding="utf-8")
    r1 = update_boostusage_table_from_csv(p)
    assert r1["created"] == 1
    p.write_text(body, encoding="utf-8")
    r2 = update_boostusage_table_from_csv(p)
    assert r2["updated"] == 1


@pytest.mark.django_db
def test_update_githubfile_is_deleted_defaults_false(tmp_path, github_account):
    from model_bakery import baker

    repo = baker.make(
        "github_activity_tracker.GitHubRepository",
        owner_account=github_account,
        repo_name="gf-default-del",
    )
    p = tmp_path / "gf.csv"
    p.write_text(
        "owner,repo_name,file_path\n"
        f"{github_account.username},{repo.repo_name},main.cpp\n",
        encoding="utf-8",
    )
    update_githubfile_table_from_csv(p)
    from github_activity_tracker.models import GitHubFile

    gf = GitHubFile.objects.get(repo=repo, filename="main.cpp")
    assert gf.is_deleted is False


@pytest.mark.django_db
def test_update_githubfile_open_os_error(tmp_path):
    p = tmp_path / "gf.csv"
    p.write_text("owner,repo_name,file_path\na,b,c\n", encoding="utf-8")
    with patch(
        "boost_usage_tracker.update_githubfile_from_csv.Path.open",
        side_effect=OSError("io"),
    ):
        r = update_githubfile_table_from_csv(p)
    assert any("io" in e.lower() for e in r["errors"])
