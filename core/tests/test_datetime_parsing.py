"""Tests for core.utils.datetime_parsing."""

from datetime import datetime, timedelta, timezone

import pytest
from django.utils import timezone as django_timezone

from core.utils.datetime_parsing import ensure_aware_utc, parse_iso_datetime


def test_ensure_aware_utc_none():
    assert ensure_aware_utc(None) is None


def test_ensure_aware_utc_naive_becomes_utc():
    naive = datetime(2024, 6, 1, 12, 0, 0)
    assert django_timezone.is_naive(naive)
    out = ensure_aware_utc(naive)
    assert out is not None
    assert out.tzinfo == timezone.utc


def test_ensure_aware_utc_aware_converted_to_utc():
    dt = datetime(2024, 1, 1, 15, 0, 0, tzinfo=timezone(timedelta(hours=2)))
    out = ensure_aware_utc(dt)
    assert out is not None
    assert out.tzinfo == timezone.utc
    assert out.hour == 13


def test_parse_iso_datetime_empty():
    assert parse_iso_datetime(None) is None
    assert parse_iso_datetime("") is None
    assert parse_iso_datetime("   ") is None


def test_parse_iso_datetime_z_suffix():
    dt = parse_iso_datetime("2024-03-15T10:30:00Z")
    assert dt is not None
    assert dt.tzinfo is None
    assert dt.year == 2024
    assert dt.month == 3
    assert dt.day == 15
    assert dt.hour == 10
    assert dt.minute == 30
    assert dt.second == 0


def test_parse_iso_datetime_date_only():
    dt = parse_iso_datetime("2024-12-25")
    assert dt is not None
    assert dt.tzinfo is None


def test_parse_iso_datetime_with_offset_strips_tz_to_naive_utc():
    dt = parse_iso_datetime("2024-01-01T00:00:00+05:00")
    assert dt is not None
    assert dt.tzinfo is None
    assert dt.year == 2023
    assert dt.month == 12
    assert dt.day == 31
    assert dt.hour == 19
    assert dt.minute == 0
    assert dt.second == 0


def test_parse_iso_datetime_invalid_raises():
    with pytest.raises(ValueError, match="Invalid ISO datetime"):
        parse_iso_datetime("not-a-date")
