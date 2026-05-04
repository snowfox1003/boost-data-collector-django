"""Tests for import_wg21_metadata_from_csv helpers and command."""

import csv
import logging
from datetime import date
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError

import wg21_paper_tracker.management.commands.import_wg21_metadata_from_csv as mod
from wg21_paper_tracker.services import get_or_create_mailing, get_or_create_paper


def test_norm_and_normalize_title():
    assert mod._norm(None) == ""
    assert mod._normalize_title("") == ""
    assert mod._normalize_title("a\nb") == "a b"
    long_t = "x" * 2000
    assert len(mod._normalize_title(long_t)) == mod.TITLE_MAX_LENGTH


def test_resolve_mailing_date_and_document_date():
    assert mod._resolve_mailing_date("") == ("unknown", "Unknown")
    assert mod._resolve_mailing_date("2024-03")[0] == "2024-03"
    assert mod._parse_document_date("") is None
    assert mod._parse_document_date("2020-05-01") == date(2020, 5, 1)


def test_author_names_from_csv():
    assert mod._author_names_from_csv("") == []
    assert mod._author_names_from_csv("a, b") == ["a", "b"]


def test_parse_csv_import_row():
    assert mod._parse_csv_import_row({"paper_id": "", "url": "x"}) is None
    row = {
        "paper_id": " D1234 ",
        "url": "https://wg21.link/p",
        "mailing_date": "2024-01",
        "date": "2024-02-01",
        "title": "Title",
        "author": "Ann, Bob",
        "subgroup": "EWG",
    }
    parsed = mod._parse_csv_import_row(row)
    assert parsed is not None
    assert parsed.paper_id == "d1234"
    assert parsed.year == 2024
    assert len(parsed.author_names) == 2


def test_read_csv_rows_roundtrip(tmp_path):
    p = tmp_path / "m.csv"
    p.write_text(
        "paper_id,URL,Title\np9,https://u,T\n",
        encoding="utf-8",
    )
    rows = list(mod._read_csv_rows(p))
    assert rows[0]["paper_id"] == "p9"
    assert rows[0]["title"] == "T"


@pytest.mark.django_db
def test_command_missing_csv_raises(tmp_path):
    missing = tmp_path / "nope.csv"
    with pytest.raises(CommandError, match="not found"):
        call_command(
            "import_wg21_metadata_from_csv",
            csv_file=missing,
            verbosity=0,
        )


@pytest.mark.django_db
def test_command_dry_run_processes_rows(tmp_path, caplog):
    csv_path = tmp_path / "metadata.csv"
    csv_path.write_text(
        "paper_id,url,title,author,date,mailing_date,subgroup\n"
        "z1,https://example.com/z,T,A,2024-02-01,2024-02,\n",
        encoding="utf-8",
    )
    with caplog.at_level(logging.INFO):
        call_command(
            "import_wg21_metadata_from_csv",
            csv_file=csv_path,
            dry_run=True,
            verbosity=0,
        )
    assert "Dry run" in caplog.text


@pytest.mark.django_db
def test_command_import_creates_paper(tmp_path):
    csv_path = tmp_path / "meta.csv"
    csv_path.write_text(
        "paper_id,url,title,author,date,mailing_date,subgroup\n"
        "ab12,https://wg21.example/ab,T,,2024-03-01,,\n",
        encoding="utf-8",
    )
    call_command(
        "import_wg21_metadata_from_csv",
        csv_file=csv_path,
        verbosity=0,
    )
    from wg21_paper_tracker.models import WG21Paper

    assert WG21Paper.objects.filter(paper_id="ab12").exists()


@pytest.mark.django_db
def test_command_skips_bad_rows_logged(tmp_path):
    csv_path = tmp_path / "bad.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["paper_id", "url", "title", "mailing_date", "date"],
        )
        w.writeheader()
        w.writerow(
            {
                "paper_id": "",
                "url": "",
                "title": "",
                "mailing_date": "",
                "date": "",
            }
        )

    call_command("import_wg21_metadata_from_csv", csv_file=csv_path, verbosity=0)


@pytest.mark.django_db
def test_update_paper_on_integrity_error_updates_existing():
    mailing, _ = get_or_create_mailing("unknown", "Unknown")
    paper, _ = get_or_create_paper(
        paper_id="dupx",
        url="https://old",
        title="Old",
        document_date=None,
        mailing=mailing,
        subgroup="",
        year=2024,
    )
    stats = {"skipped": 0, "papers_updated": 0}
    parsed = mod._CsvImportRow(
        paper_id="dupx",
        url="https://new",
        mailing_date="unknown",
        mailing_title="Unknown",
        document_date=None,
        year=2024,
        title="New title",
        subgroup="sub",
        author_names=[],
    )
    mod._update_paper_on_integrity_error(parsed, IntegrityError("dup"), stats)
    paper.refresh_from_db()
    assert paper.url == "https://new"
    assert paper.title == "New title"
    assert stats["papers_updated"] == 1


@pytest.mark.django_db
def test_upsert_row_general_exception_increments_skipped():
    stats = {
        "skipped": 0,
        "papers_updated": 0,
        "mailings_created": 0,
        "papers_created": 0,
    }
    parsed = mod._CsvImportRow(
        paper_id="e1",
        url="https://u",
        mailing_date="unknown",
        mailing_title="Unknown",
        document_date=None,
        year=None,
        title="T",
        subgroup="",
        author_names=[],
    )

    def boom(*a, **k):
        raise RuntimeError("fail")

    with patch.object(mod, "get_or_create_mailing", side_effect=boom):
        mod._upsert_paper_from_csv_row(parsed, stats)

    assert stats["skipped"] == 1
