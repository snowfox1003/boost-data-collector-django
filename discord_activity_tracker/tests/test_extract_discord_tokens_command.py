"""Tests for extract_discord_tokens management command."""

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


@patch(
    "discord_activity_tracker.management.commands.extract_discord_tokens.extract_and_save_discord_internal_tokens",
    return_value="discord-tok",
)
@patch(
    "discord_activity_tracker.management.commands.extract_discord_tokens._resolve_discord_chrome_profile_root",
)
def test_extract_discord_tokens_command_success(
    mock_resolve_profile, mock_extract_and_save, tmp_path
):
    profile = tmp_path / "chrome_profile"
    profile.mkdir()
    mock_resolve_profile.return_value = profile
    out = StringIO()
    call_command("extract_discord_tokens", stdout=out)
    mock_extract_and_save.assert_called_once()
    assert "Saved Discord session credentials" in out.getvalue()


@patch(
    "discord_activity_tracker.management.commands.extract_discord_tokens.extract_and_save_discord_internal_tokens",
    return_value=None,
)
@patch(
    "discord_activity_tracker.management.commands.extract_discord_tokens._resolve_discord_chrome_profile_root",
)
def test_extract_discord_tokens_command_failure(
    mock_resolve_profile, mock_extract_and_save, tmp_path
):
    profile = tmp_path / "chrome_profile"
    profile.mkdir()
    mock_resolve_profile.return_value = profile
    with pytest.raises(CommandError, match="Failed to load session credentials"):
        call_command("extract_discord_tokens")
    mock_extract_and_save.assert_called_once()


def test_extract_discord_tokens_command_missing_profile(settings, tmp_path):
    settings.DISCORD_CHROME_PROFILE_PATH = str(tmp_path / "missing_profile")
    with pytest.raises(CommandError, match="Session storage not found"):
        call_command("extract_discord_tokens")
