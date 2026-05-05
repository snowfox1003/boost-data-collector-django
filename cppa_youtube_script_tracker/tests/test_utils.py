"""Tests for cppa_youtube_script_tracker.utils."""

from cppa_youtube_script_tracker.utils import (
    UNKNOWN_SPEAKER_NAME,
    build_speaker_external_id,
    clean_text,
    extract_speakers_from_description,
    extract_speakers_from_title,
    extract_speakers_from_transcript_text,
    resolve_speakers,
)
from cppa_youtube_script_tracker import utils as utils_mod


def test_clean_text_none_and_unicode():
    assert clean_text(None) == ""
    assert clean_text("a\x00b") == "ab"
    assert clean_text("don\u2019t") == "don't"
    assert clean_text("  x  ") == "x"


def test_build_speaker_external_id_channel_video_name_fallback():
    assert build_speaker_external_id("Jane Doe", channel_id="ch1") == (
        "youtube:channel:ch1:speaker:jane_doe"
    )
    assert build_speaker_external_id("Jane Doe", video_id="v9") == (
        "youtube:video:v9:speaker:jane_doe"
    )
    assert build_speaker_external_id("Jane Doe") == "youtube:name:jane_doe"
    assert build_speaker_external_id("!!!") == "youtube:name:unknown"


def test_extract_speakers_from_description_speaker_colon():
    desc = "Speaker: Alice Smith\n\nMore text"
    assert extract_speakers_from_description(desc) == ["Alice Smith"]


def test_extract_speakers_from_description_triplet_fourth_line():
    desc = (
        "line1\nline2\nline3\n"
        "My Talk Title — Bob Builder — CppCon Channel Extra\n"
        "footer"
    )
    out = extract_speakers_from_description(
        desc,
        title="My Talk Title",
        channel_title="CppCon Channel",
    )
    assert "Bob Builder" in out


def test_extract_speakers_from_description_intro_pattern():
    desc = "Hello\nMy name is Carol Writer.\nThanks"
    assert extract_speakers_from_description(desc) == ["Carol Writer"]


def test_extract_speakers_from_description_empty():
    assert extract_speakers_from_description("") == []
    assert extract_speakers_from_description("   ") == []


def test_extract_speakers_from_title_middle_segment():
    title = "Patterns — Dave Engineer — Meeting C++"
    assert extract_speakers_from_title(title, channel_title="Meeting C++") == [
        "Dave Engineer"
    ]


def test_extract_speakers_from_title_empty():
    assert extract_speakers_from_title("") == []


def test_extract_speakers_from_transcript_text_limits_and_dedupe():
    early = "I am Erin Speaker. " + ("x" * 100)
    assert extract_speakers_from_transcript_text(early) == ["Erin Speaker"]
    assert extract_speakers_from_transcript_text("") == []


def test_extract_middle_name_from_triplet_no_confidence_match():
    assert (
        utils_mod._extract_middle_name_from_triplet(
            "Alpha — Beta — Gamma",
            title="Other Title",
            channel_title="Other Channel",
        )
        == ""
    )


def test_resolve_speakers_priority_description_then_title_then_transcript():
    assert resolve_speakers(
        title="t",
        description="Speaker: Only Desc",
        transcript_text="I am Trans Only",
    ) == ["Only Desc"]

    assert resolve_speakers(
        title="A — Name Here — Chan",
        description="",
        channel_title="Chan",
        transcript_text="I am Trans Only",
    ) == ["Name Here"]

    assert resolve_speakers(
        title="plain",
        description="",
        transcript_text="My name is From Trans",
    ) == ["From Trans"]

    assert resolve_speakers(title="", description="", transcript_text="") == [
        UNKNOWN_SPEAKER_NAME
    ]
