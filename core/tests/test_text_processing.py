"""Tests for core.utils.text_processing."""

import pytest

from core.utils.text_processing import (
    SLACK_GREETING_WORDS,
    attr_str,
    clean_text,
    filter_sentence,
    truncate_content,
    validate_content_length,
)


def test_attr_str():
    assert attr_str(None) == ""
    assert attr_str([]) == ""
    assert attr_str(["/a", "/b"]) == "/a"
    assert attr_str("/path") == "/path"


def test_clean_text_empty():
    assert clean_text(None) == ""
    assert clean_text("") == ""


def test_clean_text_collapses_spaces_and_strips():
    assert clean_text("  a   b  ") == "a b"


def test_clean_text_remove_extra_spaces_false_keeps_newlines():
    raw = "line1\n\n\nline2"
    out = clean_text(raw, remove_extra_spaces=False)
    assert "line1" in out
    assert "line2" in out
    assert "\n" in out
    assert out.splitlines() == ["line1", "", "", "line2"]


def test_clean_text_unescapes_html_and_invisible_chars():
    s = "\xadhello&nbsp;world\u200b"
    out = clean_text(s)
    assert "hello" in out
    assert "world" in out


def test_filter_sentence_empty():
    assert filter_sentence("") == ""
    assert filter_sentence("   ") == ""


def test_filter_sentence_removes_greeting():
    out = filter_sentence("Hi there, can you help?")
    assert "help" in out


def test_filter_sentence_too_few_words_returns_empty():
    assert filter_sentence("ok sure", min_words_after=3) == ""


def test_filter_sentence_custom_word_lists():
    out = filter_sentence(
        "alpha beta gamma delta",
        greeting_words=["alpha"],
        unessential_words=["beta"],
        min_words_after=2,
    )
    assert "gamma" in out


def test_validate_content_length():
    assert validate_content_length(None) is False
    assert validate_content_length("short") is False
    long_enough = "x" * 50
    assert validate_content_length(long_enough) is True
    assert validate_content_length("  " + long_enough) is True


def test_slack_constants_non_empty():
    assert "hello" in SLACK_GREETING_WORDS


def test_truncate_content_short_unchanged():
    assert truncate_content("hi", max_length=100) == "hi"


def test_truncate_content_long_adds_ellipsis():
    s = "x" * 50
    out = truncate_content(s, max_length=10)
    assert out.endswith("...")
    assert len(out) == 10


def test_truncate_content_max_length_at_most_three():
    assert truncate_content("abcdef", max_length=2) == "ab"


def test_truncate_content_negative_max_length_raises():
    with pytest.raises(ValueError, match="max_length must be non-negative"):
        truncate_content("hello", max_length=-1)
