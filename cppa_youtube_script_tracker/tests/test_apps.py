"""App config smoke test."""

from cppa_youtube_script_tracker.apps import CppaYoutubeScriptTrackerConfig


def test_app_config_metadata():
    assert CppaYoutubeScriptTrackerConfig.name == "cppa_youtube_script_tracker"
    assert "YouTube" in CppaYoutubeScriptTrackerConfig.verbose_name
