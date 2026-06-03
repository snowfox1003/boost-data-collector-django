"""Tests for :mod:`core.activity_types`."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.activity_types import (
    ActivityType,
    SourceSystem,
    activity_record_to_legacy_dict,
    actor_external_id,
    ensure_activity_occurred_at,
    migrate_legacy_activity_fields,
    parse_activity_occurred_at,
)


def test_parse_activity_occurred_at_canonical_z() -> None:
    dt = parse_activity_occurred_at("2024-01-01T00:00:00Z")
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.astimezone(timezone.utc).year == 2024


def test_parse_activity_occurred_at_discord_fractional_z() -> None:
    dt = parse_activity_occurred_at("2024-01-01T00:00:00.0000000Z")
    assert dt is not None
    assert dt.tzinfo is not None


def test_parse_activity_occurred_at_empty_returns_none() -> None:
    assert parse_activity_occurred_at("") is None
    assert parse_activity_occurred_at("   ") is None


def test_ensure_activity_occurred_at_naive_becomes_aware_utc() -> None:
    naive = datetime(2024, 6, 1, 12, 0, 0)
    out = ensure_activity_occurred_at(naive)
    assert out.tzinfo is not None
    assert out.astimezone(timezone.utc).hour == 12


def test_ensure_activity_occurred_at_converts_non_utc() -> None:
    est = timezone(timedelta(hours=-5))
    eastern = datetime(2024, 6, 1, 8, 0, 0, tzinfo=est)
    out = ensure_activity_occurred_at(eastern)
    assert out.tzinfo == timezone.utc
    assert out.timestamp() == eastern.timestamp()
    assert out.hour == 13


def test_activity_type_factories_and_equality() -> None:
    assert ActivityType.github_issue() == ActivityType("github.issue")
    assert ActivityType.discord_message("Reply") == ActivityType("discord.Reply")
    assert str(ActivityType.discord_message("Default")) == "discord.Default"


def test_actor_external_id_coerces_int() -> None:
    assert str(actor_external_id(7)) == "7"


def test_migrate_legacy_activity_fields_from_strings() -> None:
    source, occurred, atype, actor = migrate_legacy_activity_fields(
        source_system="discord",
        occurred_at="2024-01-01T00:00:00.0000000Z",
        activity_type="discord.Reply",
        actor_external_id_raw=7,
    )
    assert source is SourceSystem.DISCORD
    assert occurred is not None
    assert atype == ActivityType.discord_message("Reply")
    assert str(actor) == "7"


def test_activity_record_to_legacy_dict_round_trip() -> None:
    source, occurred, atype, actor = migrate_legacy_activity_fields(
        source_system=SourceSystem.GITHUB.value,
        occurred_at="2024-06-01T12:00:00Z",
        activity_type=ActivityType.github_issue(),
        actor_external_id_raw="42",
    )
    legacy = activity_record_to_legacy_dict(
        source_system=source,
        external_id="1:issue:2",
        occurred_at=occurred,
        activity_type=atype,
        actor_id=actor,
        source_url=None,
        summary="title",
    )
    assert legacy["source_system"] == "github"
    assert legacy["activity_type"] == "github.issue"
    assert legacy["actor_external_id"] == "42"
    assert legacy["occurred_at"].endswith("Z")
    assert legacy["external_id"] == "1:issue:2"


def test_migrate_unknown_source_system_raises() -> None:
    with pytest.raises(ValueError, match="unknown source_system"):
        migrate_legacy_activity_fields(
            source_system="slack",
            occurred_at="",
            activity_type="slack.message",
            actor_external_id_raw="",
        )
