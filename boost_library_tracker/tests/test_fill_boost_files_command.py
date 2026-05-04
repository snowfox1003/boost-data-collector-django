"""Tests for fill_boost_files management command."""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from model_bakery import baker

from boost_library_tracker import services as bl_services
from boost_library_tracker.management.commands.fill_boost_files import _normalize_name
from boost_library_tracker.models import BoostLibrary
from github_activity_tracker.models import GitHubFile


def test_normalize_name_empty_and_repo_style():
    assert _normalize_name("") == ""
    assert _normalize_name(" Math / Lib ") == "math___lib"


@pytest.mark.django_db
def test_fill_boost_files_single_library_dry_run(
    boost_library_repository, github_account
):
    boost_library_repository.repo_name = "singleton"
    boost_library_repository.save()
    baker.make(
        BoostLibrary,
        repo=boost_library_repository,
        name="OnlyLib",
    )
    baker.make(
        GitHubFile,
        repo=boost_library_repository,
        filename="include/boost/x.hpp",
        is_deleted=False,
    )

    out = StringIO()
    call_command("fill_boost_files", "--dry-run", stdout=out)
    text = out.getvalue()
    assert "Dry run" in text
    assert "files linked: 1" in text


@pytest.mark.django_db
def test_fill_boost_files_writes_csv(
    tmp_path, boost_library_repository, github_account
):
    boost_library_repository.repo_name = "singleton"
    boost_library_repository.save()
    baker.make(BoostLibrary, repo=boost_library_repository, name="L")
    baker.make(
        GitHubFile,
        repo=boost_library_repository,
        filename="orphan.hpp",
        is_deleted=False,
    )
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    with patch(
        "boost_library_tracker.management.commands.fill_boost_files.get_workspace_path",
        return_value=ws,
    ):
        call_command("fill_boost_files", "--dry-run", stdout=StringIO())
    csv_path = ws / "missing_library_files.csv"
    assert csv_path.exists()
    body = csv_path.read_text(encoding="utf-8")
    assert "orphan.hpp" in body


@pytest.mark.django_db
def test_fill_boost_files_skips_multi_library_non_math_repo(
    boost_library_repository, github_account
):
    boost_library_repository.repo_name = "not-math"
    boost_library_repository.save()
    baker.make(BoostLibrary, repo=boost_library_repository, name="A")
    baker.make(BoostLibrary, repo=boost_library_repository, name="B")

    out = StringIO()
    call_command("fill_boost_files", "--dry-run", stdout=out)
    text = out.getvalue()
    assert "repos with chosen library: 0" in text


@pytest.mark.django_db
def test_fill_boost_files_math_repo_uses_math_library(github_account):
    parent = baker.make(
        "github_activity_tracker.GitHubRepository",
        owner_account=github_account,
        repo_name="math",
        stars=0,
        forks=0,
    )
    repo, _ = bl_services.get_or_create_boost_library_repo(parent)
    baker.make(BoostLibrary, repo=repo, name="Other")
    baker.make(BoostLibrary, repo=repo, name="Math")
    baker.make(
        GitHubFile,
        repo=repo,
        filename="f.hpp",
        is_deleted=False,
    )

    out = StringIO()
    call_command("fill_boost_files", "--dry-run", stdout=out)
    text = out.getvalue()
    assert "repos with chosen library: 1" in text
