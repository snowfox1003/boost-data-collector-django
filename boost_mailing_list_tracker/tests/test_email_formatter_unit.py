"""Direct tests for boost_mailing_list_tracker.email_formatter."""

from boost_mailing_list_tracker.email_formatter import (
    format_email,
    _deobfuscate_address,
    _extract_list_name,
    _extract_sender,
    _extract_url_tail_id,
    _normalize_sent_at,
)


def test_extract_url_tail_id():
    assert _extract_url_tail_id("") == ""
    assert _extract_url_tail_id("https://x/y/z") == "z"
    assert _extract_url_tail_id("plain") == "plain"


def test_extract_list_name_patterns():
    url = "https://lists.boost.org/list/foo/thread/abc/"
    assert _extract_list_name(url) == "foo"
    assert _extract_list_name("", "archives@lists.boost.org") != ""
    assert _extract_list_name("no-match") == ""


def test_deobfuscate_address():
    assert _deobfuscate_address("") == ""
    assert "@" in _deobfuscate_address("user (a) lists.boost.org")


def test_extract_sender_variants():
    addr, name = _extract_sender(
        {"from": '"Alice" <alice@example.com>', "sender_address": "", "sender_name": ""}
    )
    assert addr.endswith("example.com")
    assert name


def test_normalize_sent_at_rfc2822():
    raw = {"date": "Sat, 03 Apr 2010 18:32:00 +0200"}
    out = _normalize_sent_at(raw)
    assert out is not None
    assert "2010" in out


def test_format_email_shapes():
    assert format_email([]) == []
    assert format_email("x") == []
    one = format_email([{"msg_id": "a", "subject": "S"}])
    assert len(one) == 1
    assert one[0]["msg_id"] == "a"

    threaded = format_email(
        {
            "thread_info": {"thread_id": "tid"},
            "messages": [{"message_id": "m1", "subject": "Hi"}],
        }
    )
    assert threaded[0]["thread_id"] == "tid"
