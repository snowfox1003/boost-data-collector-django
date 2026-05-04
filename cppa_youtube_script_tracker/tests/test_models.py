"""Tests for cppa_youtube_script_tracker.models __str__ and basics."""

import pytest
from model_bakery import baker

from cppa_youtube_script_tracker.models import (
    CppaTags,
    YouTubeChannel,
    YouTubeVideo,
    YouTubeVideoSpeaker,
    YouTubeVideoTags,
)


@pytest.mark.django_db
def test_youtube_channel_str_with_and_without_title():
    ch = baker.make(YouTubeChannel, channel_id="c1", channel_title="CppCon")
    assert str(ch) == "CppCon"
    ch2 = baker.make(YouTubeChannel, channel_id="c2", channel_title="")
    assert str(ch2) == "c2"


@pytest.mark.django_db
def test_youtube_video_str():
    v = baker.make(YouTubeVideo, video_id="v1", title="Talk")
    assert str(v) == "Talk"
    v2 = baker.make(YouTubeVideo, video_id="v2", title="")
    assert str(v2) == "v2"


@pytest.mark.django_db
def test_join_models_str():
    video = baker.make(YouTubeVideo, video_id="vid")
    speaker = baker.make(
        "cppa_user_tracker.YoutubeSpeaker",
        external_id="e1",
        display_name="S",
    )
    vs = baker.make(YouTubeVideoSpeaker, video=video, speaker=speaker)
    assert "vid" in str(vs) and "speaker" in str(vs)

    tag = baker.make(CppaTags, tag_name="t1")
    vt = baker.make(YouTubeVideoTags, youtube_video=video, cppa_tag=tag)
    assert "vid" in str(vt) and "tag" in str(vt)


@pytest.mark.django_db
def test_cppa_tags_str():
    t = baker.make(CppaTags, tag_name="modules")
    assert str(t) == "modules"
