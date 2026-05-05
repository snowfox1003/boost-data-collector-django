"""Tests for import_boost_file_from_csv management command."""

from __future__ import annotations

import csv
from io import StringIO

import pytest
from django.core.management import call_command
from model_bakery import baker

from boost_library_tracker import services as bl_services
from boost_library_tracker.management.commands.import_boost_file_from_csv import (
    _link_file_for_path,
)
from boost_library_tracker.models import BoostFile, BoostLibrary
from github_activity_tracker.models import GitHubFile


@pytest.mark.django_db
def test_import_boost_file_from_csv_missing_file(tmp_path):
    missing = tmp_path / "nope.csv"
    out = StringIO()
    err = StringIO()
    call_command(
        "import_boost_file_from_csv",
        str(missing),
        stdout=out,
        stderr=err,
    )
    assert "not found" in out.getvalue().lower()


@pytest.mark.django_db
def test_import_boost_file_from_csv_dry_run_missing_library(tmp_path, boost_library):
    csv_path = tmp_path / "link.csv"
    csv_path.write_text(
        "library_name,file_name\nno_such_lib,\n",
        encoding="utf-8",
    )
    out = StringIO()
    call_command(
        "import_boost_file_from_csv",
        str(csv_path),
        "--dry-run",
        stdout=out,
    )
    assert "Dry run" in out.getvalue()


@pytest.mark.django_db
def test_import_boost_file_from_csv_ambiguous_library(tmp_path, github_account):
    def mk_repo(name_suffix: str):
        parent = baker.make(
            "github_activity_tracker.GitHubRepository",
            owner_account=github_account,
            repo_name=f"boost-{name_suffix}",
            stars=0,
            forks=0,
        )
        bl_repo, _ = bl_services.get_or_create_boost_library_repo(parent)
        return bl_repo

    repo_a = mk_repo("a")
    repo_b = mk_repo("b")
    dup = "DupLib"
    baker.make(BoostLibrary, repo=repo_a, name=dup)
    baker.make(BoostLibrary, repo=repo_b, name=dup)
    csv_path = tmp_path / "link.csv"
    csv_path.write_text(
        f"library_name,file_name\n{dup},foo.hpp\n",
        encoding="utf-8",
    )
    err_csv = tmp_path / "errors.csv"
    out = StringIO()
    call_command(
        "import_boost_file_from_csv",
        str(csv_path),
        "--errors",
        str(err_csv),
        stdout=out,
    )
    assert err_csv.exists()
    rows = list(csv.DictReader(err_csv.open(encoding="utf-8")))
    assert len(rows) == 1
    assert "ambiguous" in rows[0].get("library_not_found", "").lower()


@pytest.mark.django_db
def test_import_boost_file_from_csv_links_existing_header(
    tmp_path, boost_library_repository, boost_library
):
    gf = baker.make(
        GitHubFile,
        repo=boost_library_repository,
        filename="include/boost/foo.hpp",
        is_deleted=False,
    )
    csv_path = tmp_path / "link.csv"
    csv_path.write_text(
        f"library_name,file_name\n{boost_library.name},include/boost/foo.hpp\n",
        encoding="utf-8",
    )
    out = StringIO()
    call_command("import_boost_file_from_csv", str(csv_path), stdout=out)
    assert "files linked: 1" in out.getvalue() or "linked: 1" in out.getvalue()
    gf.refresh_from_db()
    assert BoostFile.objects.filter(
        github_file=gf, library_id=boost_library.pk
    ).exists()


@pytest.mark.django_db
def test_link_file_empty_path_noops(boost_library_repository, boost_library):
    stats = {"files_added": 0, "files_not_found": 0}
    rows: list = []
    _link_file_for_path(boost_library_repository, boost_library, "", stats, rows, {})
    assert stats == {"files_added": 0, "files_not_found": 0}


@pytest.mark.django_db
def test_import_csv_dry_run_counts_existing_file(
    tmp_path, boost_library_repository, boost_library
):
    baker.make(
        GitHubFile,
        repo=boost_library_repository,
        filename="found.hpp",
        is_deleted=False,
    )
    csv_path = tmp_path / "link.csv"
    csv_path.write_text(
        f"library_name,file_name\n{boost_library.name},found.hpp\n",
        encoding="utf-8",
    )
    out = StringIO()
    call_command(
        "import_boost_file_from_csv",
        str(csv_path),
        "--dry-run",
        stdout=out,
    )
    assert "files linked: 1" in out.getvalue()


@pytest.mark.django_db
def test_import_csv_blank_library_skipped(tmp_path):
    csv_path = tmp_path / "link.csv"
    csv_path.write_text("library_name,file_name\n,orphan.hpp\n", encoding="utf-8")
    out = StringIO()
    call_command("import_boost_file_from_csv", str(csv_path), stdout=out)
    assert "Rows processed: 0" in out.getvalue()


@pytest.mark.django_db
def test_import_csv_dry_run_missing_file_row_errors_csv(
    tmp_path, boost_library_repository, boost_library
):
    csv_path = tmp_path / "link.csv"
    csv_path.write_text(
        f"library_name,file_name\n{boost_library.name},nope.hpp\n",
        encoding="utf-8",
    )
    err_csv = tmp_path / "errors.csv"
    out = StringIO()
    call_command(
        "import_boost_file_from_csv",
        str(csv_path),
        "--dry-run",
        "--errors",
        str(err_csv),
        stdout=out,
    )
    rows = list(csv.DictReader(err_csv.open(encoding="utf-8")))
    assert len(rows) == 1
    assert rows[0]["path_not_found"] == "nope.hpp"


@pytest.mark.django_db
def test_import_boost_file_from_csv_not_found_lists_similar_paths(
    tmp_path, boost_library_repository, boost_library
):
    baker.make(
        GitHubFile,
        repo=boost_library_repository,
        filename="libs/detail/bar_impl.hpp",
        is_deleted=False,
    )
    csv_path = tmp_path / "link.csv"
    csv_path.write_text(
        f"library_name,file_name\n{boost_library.name},libs/detail/bar\n",
        encoding="utf-8",
    )
    err_csv = tmp_path / "errors.csv"
    out = StringIO()
    call_command(
        "import_boost_file_from_csv",
        str(csv_path),
        "--errors",
        str(err_csv),
        stdout=out,
    )
    assert err_csv.exists()
    text = err_csv.read_text(encoding="utf-8")
    assert "libs/detail/bar" in text
    assert "bar_impl.hpp" in text


@pytest.mark.django_db
def test_import_boost_file_from_csv_not_found_no_candidates(
    tmp_path, boost_library_repository, boost_library
):
    csv_path = tmp_path / "link.csv"
    csv_path.write_text(
        f"library_name,file_name\n{boost_library.name},only/missing/path.hpp\n",
        encoding="utf-8",
    )
    err_csv = tmp_path / "errors.csv"
    call_command(
        "import_boost_file_from_csv",
        str(csv_path),
        "--errors",
        str(err_csv),
        stdout=StringIO(),
    )
    rows = list(csv.DictReader(err_csv.open(encoding="utf-8")))
    assert len(rows) == 1
    assert rows[0]["supported_files"] == ""
