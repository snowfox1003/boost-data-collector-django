"""Tests for boost_usage_tracker.update_created_repos_by_language."""

import logging
from unittest.mock import patch

import pytest
from model_bakery import baker

from boost_usage_tracker.update_created_repos_by_language import (
    update_created_repos_by_language,
)
from github_activity_tracker.models import CreatedReposByLanguage


@pytest.mark.django_db
def test_update_created_repos_by_language_requires_languages():
    """Returns error when no env/arg languages are provided."""
    with patch.dict("os.environ", {"REPO_COUNT_LANGUAGES": ""}, clear=False):
        result = update_created_repos_by_language(
            languages_csv="",
            start_year=2024,
            end_year=2024,
        )
    assert result["rows_processed"] == 0
    assert result["errors"]


@pytest.mark.django_db
def test_update_created_repos_by_language_upserts_rows():
    """Upserts yearly rows for languages existing in Language table."""
    cpp = baker.make("github_activity_tracker.Language", name="C++")

    def fake_count(_client, query: str) -> int:
        if "stars:>10" in query:
            return 12
        return 120

    with (
        patch("boost_usage_tracker.update_created_repos_by_language.get_github_client"),
        patch(
            "boost_usage_tracker.update_created_repos_by_language._count_items_from_git",
            side_effect=fake_count,
        ),
    ):
        result = update_created_repos_by_language(
            languages_csv="C++",
            start_year=2024,
            end_year=2025,
            stars_min=10,
        )

    assert result["errors"] == []
    assert result["rows_processed"] == 2
    assert result["created"] == 2
    assert result["updated"] == 0

    rows = list(
        CreatedReposByLanguage.objects.filter(  # pylint: disable=no-member
            language=cpp
        ).order_by("year")
    )
    assert [r.year for r in rows] == [2024, 2025]
    assert all(r.all_repos == 120 for r in rows)
    assert all(r.significant_repos == 12 for r in rows)

    # second run updates existing rows
    with (
        patch("boost_usage_tracker.update_created_repos_by_language.get_github_client"),
        patch(
            "boost_usage_tracker.update_created_repos_by_language._count_items_from_git",
            side_effect=lambda _client, q: 130 if "stars:>10" not in q else 13,
        ),
    ):
        second = update_created_repos_by_language(
            languages_csv="C++",
            start_year=2024,
            end_year=2025,
            stars_min=10,
        )

    assert second["created"] == 0
    assert second["updated"] == 2
    rows = list(
        CreatedReposByLanguage.objects.filter(  # pylint: disable=no-member
            language=cpp
        ).order_by("year")
    )
    assert all(r.all_repos == 130 for r in rows)
    assert all(r.significant_repos == 13 for r in rows)


@pytest.mark.django_db
def test_update_created_repos_invalid_year_range():
    r = update_created_repos_by_language(
        languages_csv="C++",
        start_year=2025,
        end_year=2020,
    )
    assert r["rows_processed"] == 0
    assert any("Invalid year range" in e for e in r["errors"])


@pytest.mark.django_db
def test_update_created_repos_fail_on_missing_language():
    r = update_created_repos_by_language(
        languages_csv="AbsolutelyFakeLangXYZ",
        start_year=2024,
        end_year=2024,
        fail_on_missing_language=True,
    )
    assert r["rows_processed"] == 0
    assert any("not found" in e.lower() for e in r["errors"])


@pytest.mark.django_db
def test_update_created_repos_missing_language_warns_and_skips(caplog):
    caplog.set_level(logging.WARNING)
    r = update_created_repos_by_language(
        languages_csv="GhostLang",
        start_year=2024,
        end_year=2024,
        fail_on_missing_language=False,
    )
    assert r["rows_processed"] == 0
    assert any("Skipping languages" in rec.message for rec in caplog.records)


@pytest.mark.django_db
def test_update_created_repos_dedupes_language_list():
    cpp = baker.make("github_activity_tracker.Language", name="C++")

    with (
        patch("boost_usage_tracker.update_created_repos_by_language.get_github_client"),
        patch(
            "boost_usage_tracker.update_created_repos_by_language._count_items_from_git",
            return_value=5,
        ),
    ):
        result = update_created_repos_by_language(
            languages_csv="C++, C++ , C++",
            start_year=2024,
            end_year=2024,
            stars_min=10,
        )

    assert result["errors"] == []
    assert result["languages_requested"] == ["C++"]
    assert result["rows_processed"] == 1
    assert CreatedReposByLanguage.objects.filter(  # pylint: disable=no-member
        language=cpp, year=2024
    ).exists()


@pytest.mark.django_db
def test_update_created_repos_per_year_exception_recorded():
    rust_lang = baker.make("github_activity_tracker.Language", name="Rust")

    def boom(_client, _query):
        raise RuntimeError("api")

    with (
        patch("boost_usage_tracker.update_created_repos_by_language.get_github_client"),
        patch(
            "boost_usage_tracker.update_created_repos_by_language._count_items_from_git",
            side_effect=boom,
        ),
    ):
        result = update_created_repos_by_language(
            languages_csv="Rust",
            start_year=2023,
            end_year=2024,
            stars_min=10,
        )

    assert result["rows_processed"] == 0
    assert len(result["errors"]) == 2
    assert all("Rust" in e for e in result["errors"])
    assert (
        CreatedReposByLanguage.objects.filter(  # pylint: disable=no-member
            language=rust_lang
        ).count()
        == 0
    )


@pytest.mark.django_db
def test_update_created_repos_optional_sleep_called():
    go_lang = baker.make("github_activity_tracker.Language", name="Go")

    with (
        patch("boost_usage_tracker.update_created_repos_by_language.get_github_client"),
        patch(
            "boost_usage_tracker.update_created_repos_by_language._count_items_from_git",
            return_value=1,
        ),
        patch(
            "boost_usage_tracker.update_created_repos_by_language.time.sleep"
        ) as m_sleep,
    ):
        update_created_repos_by_language(
            languages_csv="Go",
            start_year=2022,
            end_year=2022,
            sleep_seconds=0.01,
        )

    assert m_sleep.called
    assert CreatedReposByLanguage.objects.filter(  # pylint: disable=no-member
        language=go_lang, year=2022
    ).exists()
