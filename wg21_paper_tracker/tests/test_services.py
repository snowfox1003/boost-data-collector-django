"""Tests for wg21_paper_tracker.services."""

from datetime import date
from unittest.mock import patch

import pytest

from wg21_paper_tracker.services import (
    get_or_create_mailing,
    get_or_create_paper,
    get_or_create_paper_author,
    mark_paper_downloaded,
)


# --- get_or_create_mailing ---


@pytest.mark.django_db
def test_get_or_create_mailing_creates_new():
    """get_or_create_mailing creates new mailing and returns (mailing, True)."""
    m, created = get_or_create_mailing("2025-01", "2025-01 pre-meeting mailing")
    assert created is True
    assert m.mailing_date == "2025-01"
    assert m.title == "2025-01 pre-meeting mailing"


@pytest.mark.django_db
def test_get_or_create_mailing_gets_existing():
    """get_or_create_mailing returns existing mailing and (mailing, False)."""
    get_or_create_mailing("2025-01", "Original title")
    m2, created2 = get_or_create_mailing("2025-01", "Updated title")
    assert created2 is False
    assert m2.mailing_date == "2025-01"
    assert m2.title == "Updated title"  # title is updated when different


@pytest.mark.django_db
def test_get_or_create_mailing_updates_title_when_different():
    """get_or_create_mailing updates title when existing has different title."""
    get_or_create_mailing("2025-02", "Old title")
    m, _ = get_or_create_mailing("2025-02", "New title")
    m.refresh_from_db()
    assert m.title == "New title"


# --- get_or_create_paper ---


@pytest.mark.django_db
@patch("wg21_paper_tracker.services.get_or_create_wg21_paper_author_profile")
def test_get_or_create_paper_creates_new(mock_profile, db):
    """get_or_create_paper creates new paper and returns (paper, True)."""
    mailing, _ = get_or_create_mailing("2025-01", "Title")
    paper, created = get_or_create_paper(
        paper_id="p1000r0",
        url="https://example.com/p1000r0.pdf",
        title="A paper",
        document_date=date(2025, 1, 15),
        mailing=mailing,
        subgroup="SG1",
        author_names=None,
        year=2025,
    )
    assert created is True
    assert paper.paper_id == "p1000r0"
    assert paper.title == "A paper"
    assert paper.year == 2025
    assert paper.mailing_id == mailing.id
    assert paper.subgroup == "SG1"
    mock_profile.assert_not_called()


@pytest.mark.django_db
@patch("wg21_paper_tracker.services.get_or_create_wg21_paper_author_profile")
@patch("wg21_paper_tracker.services.get_or_create_paper_author")
def test_get_or_create_paper_calls_author_profile_for_each_author(
    mock_get_or_create_paper_author, mock_profile, db
):
    """get_or_create_paper calls get_or_create_wg21_paper_author_profile and get_or_create_paper_author for each author."""
    from unittest.mock import MagicMock

    alice_profile = MagicMock()
    alice_profile.pk = 1
    bob_profile = MagicMock()
    bob_profile.pk = 2
    mock_profile.side_effect = [
        (alice_profile, True),
        (bob_profile, True),
    ]
    mock_get_or_create_paper_author.return_value = (MagicMock(), True)

    mailing, _ = get_or_create_mailing("2025-01", "Title")
    paper, created = get_or_create_paper(
        paper_id="p1000r0",
        url="https://example.com/p1000r0.pdf",
        title="A paper",
        document_date=None,
        mailing=mailing,
        author_names=["Alice", "Bob"],
        year=2025,
    )
    assert created is True
    assert mock_profile.call_count == 2
    mock_profile.assert_any_call("Alice", email=None)
    mock_profile.assert_any_call("Bob", email=None)
    assert mock_get_or_create_paper_author.call_count == 2
    mock_get_or_create_paper_author.assert_any_call(paper, alice_profile, 1)
    mock_get_or_create_paper_author.assert_any_call(paper, bob_profile, 2)


@pytest.mark.django_db
def test_get_or_create_paper_normalizes_paper_id_lowercase(db):
    """get_or_create_paper stores paper_id in lowercase."""
    mailing, _ = get_or_create_mailing("2025-01", "Title")
    paper, _ = get_or_create_paper(
        paper_id="  P3039R1  ",
        url="https://example.com/p3039r1.pdf",
        title="T",
        document_date=None,
        mailing=mailing,
        year=2025,
    )
    assert paper.paper_id == "p3039r1"


@pytest.mark.django_db
def test_get_or_create_paper_gets_existing_and_updates(db):
    """get_or_create_paper returns existing and updates fields when different."""
    mailing1, _ = get_or_create_mailing("2025-01", "M1")
    mailing2, _ = get_or_create_mailing("2025-02", "M2")
    get_or_create_paper(
        paper_id="p1000r0",
        url="https://example.com/old.pdf",
        title="Old title",
        document_date=date(2025, 1, 1),
        mailing=mailing1,
        subgroup="SG1",
        year=2025,
    )
    paper2, created2 = get_or_create_paper(
        paper_id="p1000r0",
        url="https://example.com/new.pdf",
        title="New title",
        document_date=date(2025, 2, 1),
        mailing=mailing2,
        subgroup="SG2",
        year=2025,
    )
    assert created2 is False
    paper2.refresh_from_db()
    assert paper2.url == "https://example.com/new.pdf"
    assert paper2.title == "New title"
    assert paper2.mailing_id == mailing2.id
    assert paper2.subgroup == "SG2"


@pytest.mark.django_db
def test_get_or_create_paper_year_none_stored_as_zero(db):
    """get_or_create_paper with year=None stores 0 so records can be updated later."""
    mailing, _ = get_or_create_mailing("2025-01", "Title")
    paper, _ = get_or_create_paper(
        paper_id="n5034",
        url="https://example.com/n5034.html",
        title="Draft",
        document_date=None,
        mailing=mailing,
        year=None,
    )
    assert paper.year == 0


@pytest.mark.django_db
def test_get_or_create_paper_same_paper_id_different_year_creates_two(db):
    """get_or_create_paper creates separate rows for same paper_id different year (unique_together)."""
    mailing1, _ = get_or_create_mailing("2024-11", "M1")
    mailing2, _ = get_or_create_mailing("2025-01", "M2")
    p1, c1 = get_or_create_paper(
        paper_id="sd-1",
        url="https://example.com/sd-1-2024.pdf",
        title="SD 2024",
        document_date=None,
        mailing=mailing1,
        year=2024,
    )
    p2, c2 = get_or_create_paper(
        paper_id="sd-1",
        url="https://example.com/sd-1-2025.pdf",
        title="SD 2025",
        document_date=None,
        mailing=mailing2,
        year=2025,
    )
    assert c1 is True and c2 is True
    assert p1.pk != p2.pk
    assert p1.year == 2024 and p2.year == 2025


@pytest.mark.django_db
def test_get_or_create_paper_sets_author_order(db):
    """get_or_create_paper sets author_order (1-based) on WG21PaperAuthor links."""
    mailing, _ = get_or_create_mailing("2025-01", "Title")
    paper, _ = get_or_create_paper(
        paper_id="p9999",
        url="https://example.com/p9999.pdf",
        title="Multi-author paper",
        document_date=None,
        mailing=mailing,
        author_names=["First Author", "Second Author", "Third Author"],
        year=2025,
    )
    links = list(paper.authors.order_by("author_order"))
    assert len(links) == 3
    assert links[0].author_order == 1
    assert links[1].author_order == 2
    assert links[2].author_order == 3


# --- mark_paper_downloaded ---


@pytest.mark.django_db
def test_mark_paper_downloaded_requires_year(db):
    """mark_paper_downloaded raises ValueError when year is omitted."""
    with pytest.raises(ValueError, match="year is required"):
        mark_paper_downloaded("p1000r0")


@pytest.mark.django_db
def test_mark_paper_downloaded_sets_flag(db):
    """mark_paper_downloaded sets is_downloaded=True for matching (paper_id, year)."""
    mailing, _ = get_or_create_mailing("2025-01", "Title")
    paper, _ = get_or_create_paper(
        paper_id="p1000r0",
        url="https://example.com/p.pdf",
        title="T",
        document_date=None,
        mailing=mailing,
        year=2025,
    )
    assert paper.is_downloaded is False
    mark_paper_downloaded("p1000r0", year=2025)
    paper.refresh_from_db()
    assert paper.is_downloaded is True


@pytest.mark.django_db
def test_mark_paper_downloaded_normalizes_paper_id(db):
    """mark_paper_downloaded matches case-insensitively (normalizes to lower) and by year."""
    mailing, _ = get_or_create_mailing("2025-01", "Title")
    paper, _ = get_or_create_paper(
        paper_id="p1000r0",
        url="https://example.com/p.pdf",
        title="T",
        document_date=None,
        mailing=mailing,
        year=2025,
    )
    mark_paper_downloaded("  P1000R0  ", year=2025)
    paper.refresh_from_db()
    assert paper.is_downloaded is True


# --- get_or_create_paper edge cases ---


@pytest.mark.django_db
def test_get_or_create_paper_requires_paper_id(db):
    mailing, _ = get_or_create_mailing("2025-01", "Title")
    with pytest.raises(ValueError, match="paper_id is required"):
        get_or_create_paper(
            paper_id="",
            url="https://example.com/p.pdf",
            title="T",
            document_date=None,
            mailing=mailing,
            year=2025,
        )


@pytest.mark.django_db
def test_get_or_create_paper_promotes_placeholder_year(db):
    """Placeholder row (year=0) is promoted when a real year is supplied."""
    mailing, _ = get_or_create_mailing("2025-01", "Title")
    placeholder, created_placeholder = get_or_create_paper(
        paper_id="p5000",
        url="https://example.com/p5000-draft.pdf",
        title="Draft",
        document_date=None,
        mailing=mailing,
        year=None,
    )
    assert created_placeholder is True
    assert placeholder.year == 0

    paper, created = get_or_create_paper(
        paper_id="p5000",
        url="https://example.com/p5000.pdf",
        title="Final",
        document_date=date(2025, 3, 1),
        mailing=mailing,
        year=2025,
    )
    assert created is False
    paper.refresh_from_db()
    assert paper.pk == placeholder.pk
    assert paper.year == 2025
    assert paper.title == "Final"


@pytest.mark.django_db
def test_get_or_create_paper_replaces_authors_on_update(db):
    mailing, _ = get_or_create_mailing("2025-01", "Title")
    paper, _ = get_or_create_paper(
        paper_id="p7777",
        url="https://example.com/p7777.pdf",
        title="T",
        document_date=None,
        mailing=mailing,
        author_names=["Alice"],
        year=2025,
    )
    assert paper.authors.count() == 1

    paper2, created2 = get_or_create_paper(
        paper_id="p7777",
        url="https://example.com/p7777.pdf",
        title="T",
        document_date=None,
        mailing=mailing,
        author_names=["Bob", "Carol"],
        year=2025,
    )
    assert created2 is False
    assert paper2.pk == paper.pk
    names = list(
        paper2.authors.order_by("author_order").values_list(
            "profile__display_name", flat=True
        )
    )
    assert names == ["Bob", "Carol"]


@pytest.mark.django_db
def test_get_or_create_paper_invalid_year_stored_as_zero(db):
    mailing, _ = get_or_create_mailing("2025-01", "Title")
    paper, _ = get_or_create_paper(
        paper_id="p8888",
        url="https://example.com/p8888.pdf",
        title="T",
        document_date=None,
        mailing=mailing,
        year=99999,
    )
    assert paper.year == 0


@pytest.mark.django_db
def test_mark_paper_downloaded_requires_non_empty_paper_id(db):
    with pytest.raises(ValueError, match="paper_id is required"):
        mark_paper_downloaded("", year=2025)


# --- get_or_create_paper_author ---


@pytest.mark.django_db
def test_get_or_create_paper_author_creates_and_updates_order(db):
    from cppa_user_tracker.services import get_or_create_wg21_paper_author_profile

    mailing, _ = get_or_create_mailing("2025-01", "Title")
    paper, _ = get_or_create_paper(
        paper_id="p3333",
        url="https://example.com/p3333.pdf",
        title="T",
        document_date=None,
        mailing=mailing,
        year=2025,
    )
    profile, _ = get_or_create_wg21_paper_author_profile("Author One")

    link, created = get_or_create_paper_author(paper, profile, 1)
    assert created is True
    assert link.author_order == 1

    link2, created2 = get_or_create_paper_author(paper, profile, 2)
    assert created2 is False
    link2.refresh_from_db()
    assert link2.author_order == 2


@pytest.mark.django_db
def test_get_or_create_paper_author_rejects_invalid_order(db):
    from cppa_user_tracker.services import get_or_create_wg21_paper_author_profile

    mailing, _ = get_or_create_mailing("2025-01", "Title")
    paper, _ = get_or_create_paper(
        paper_id="p4444",
        url="https://example.com/p4444.pdf",
        title="T",
        document_date=None,
        mailing=mailing,
        year=2025,
    )
    profile, _ = get_or_create_wg21_paper_author_profile("Author")
    with pytest.raises(ValueError, match="author_order must be a positive integer"):
        get_or_create_paper_author(paper, profile, 0)
