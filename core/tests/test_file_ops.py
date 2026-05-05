"""Tests for core.operations.file_ops.sanitize_filename."""

import pytest

import core.operations.file_ops as file_ops
from core.operations.file_ops import sanitize_filename


@pytest.mark.parametrize(
    ("raw", "expected_substring"),
    [
        ('a:b*c?d"e<f>g|h', "_"),
        ("foo%20bar.txt", "foo_bar"),  # spaces collapse to single underscores
        ("normal-name.txt", "normal-name.txt"),
        ("..", "downloaded_file"),
        (".", "downloaded_file"),
        ("", "downloaded_file"),
    ],
)
def test_sanitize_filename_basic(raw, expected_substring):
    out = sanitize_filename(raw)
    if expected_substring == "_":
        assert "_" in out or out == "downloaded_file"
    else:
        assert expected_substring in out or out == expected_substring


def test_sanitize_windows_reserved_com_and_lpt():
    assert "COM1_" in sanitize_filename("COM1.txt") or sanitize_filename(
        "COM1.txt"
    ).startswith("COM1_")
    out = sanitize_filename("LPT1.dat")
    assert "LPT1_" in out or out.startswith("LPT1_")


def test_windows_reserved_name_guard_and_con_prn_aux():
    assert file_ops._is_windows_reserved_name("") is False
    assert file_ops._is_windows_reserved_name("CON") is True
    assert file_ops._is_windows_reserved_name("PRN") is True
    assert file_ops._is_windows_reserved_name("AUX") is True
    out = sanitize_filename("CON")
    assert "_" in out


def test_sanitize_truncates_very_long_name():
    long_base = "a" * 250
    out = sanitize_filename(long_base + ".txt")
    assert len(out) <= 200
    assert out.endswith(".txt")


def test_sanitize_empty_after_processing_becomes_downloaded():
    assert sanitize_filename("___") == "downloaded_file"
