"""Tests for cppa_youtube_script_tracker.services."""

import pytest
from django.utils import timezone

from cppa_youtube_script_tracker.services import (
    get_or_create_channel,
    get_or_create_tag,
    get_or_create_video,
    link_speaker_to_video,
    link_tag_to_video,
    remove_speaker_links_by_name,
    update_video_transcript,
)
from cppa_user_tracker.models import YoutubeSpeaker


@pytest.mark.django_db
def test_get_or_create_channel_create_and_update_title():
    ch = get_or_create_channel("chan1", "Old")
    assert ch.channel_title == "Old"

    ch2 = get_or_create_channel("chan1", "New Title")
    assert ch2.pk == "chan1"
    ch2.refresh_from_db()
    assert ch2.channel_title == "New Title"


@pytest.mark.django_db
def test_get_or_create_channel_empty_raises():
    with pytest.raises(ValueError, match="channel_id"):
        get_or_create_channel("  ")


@pytest.mark.django_db
def test_get_or_create_video_and_parse_dates():
    ch = get_or_create_channel("c1", "Ch")
    published = timezone.now()
    video, created = get_or_create_video(
        "vid1",
        ch,
        {
            "title": "T",
            "description": "D",
            "published_at": published.isoformat(),
            "duration_seconds": 10,
            "view_count": 5,
            "scraped_at": published.isoformat(),
            "search_term": "cpp",
        },
    )
    assert created is True
    assert video.title == "T"
    assert video.duration_seconds == 10
    assert video.view_count == 5

    video2, created2 = get_or_create_video("vid1", ch, {"title": "T"})
    assert created2 is False
    assert video2.pk == "vid1"


@pytest.mark.django_db
def test_get_or_create_video_empty_id_raises():
    with pytest.raises(ValueError, match="video_id"):
        get_or_create_video(" ", None, {})


@pytest.mark.django_db
def test_update_video_transcript():
    v = get_or_create_video("v", None, {})[0]
    out = update_video_transcript(v, "/tmp/a.vtt")
    assert out.has_transcript is True
    assert out.transcript_path == "/tmp/a.vtt"


@pytest.mark.django_db
def test_link_speaker_tag_and_remove():
    v = get_or_create_video("vx", None, {})[0]
    sp = YoutubeSpeaker.objects.create(
        external_id="ext1",
        display_name="Speaker One",
    )
    join = link_speaker_to_video(v, sp)
    assert join.video_id == "vx"

    tag = get_or_create_tag("Concurrency")
    tj = link_tag_to_video(v, tag)
    assert tj.youtube_video_id == "vx"

    assert remove_speaker_links_by_name(v, "") == 0
    assert remove_speaker_links_by_name(v, "Speaker One") >= 1


@pytest.mark.django_db
def test_get_or_create_tag_normalizes_case():
    t1 = get_or_create_tag("Templates")
    t2 = get_or_create_tag("templates")
    assert t1.pk == t2.pk


@pytest.mark.django_db
def test_get_or_create_tag_empty_raises():
    with pytest.raises(ValueError, match="tag_name"):
        get_or_create_tag("   ")
