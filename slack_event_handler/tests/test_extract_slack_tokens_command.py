"""Tests for extract_slack_tokens management command."""

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


@patch(
    "slack_event_handler.management.commands.extract_slack_tokens.extract_and_save_slack_internal_tokens",
    return_value=("xc", "xd"),
)
@patch(
    "slack_event_handler.management.commands.extract_slack_tokens._resolve_chrome_profile_root",
)
def test_extract_slack_tokens_command_success(
    mock_resolve_profile, mock_extract_and_save, tmp_path
):
    profile = tmp_path / "chrome_profile"
    profile.mkdir()
    mock_resolve_profile.return_value = profile
    out = StringIO()
    call_command("extract_slack_tokens", "--team-id=T1", stdout=out)
    mock_extract_and_save.assert_called_once_with("T1")
    assert "saved to" in out.getvalue()


@patch(
    "slack_event_handler.management.commands.extract_slack_tokens.extract_and_save_slack_internal_tokens",
    return_value=None,
)
@patch(
    "slack_event_handler.management.commands.extract_slack_tokens._resolve_chrome_profile_root",
)
def test_extract_slack_tokens_command_failure(
    mock_resolve_profile, mock_extract_and_save, tmp_path
):
    profile = tmp_path / "chrome_profile"
    profile.mkdir()
    mock_resolve_profile.return_value = profile
    with pytest.raises(CommandError, match="Token extraction failed"):
        call_command("extract_slack_tokens", "--team-id=T1")
    mock_extract_and_save.assert_called_once_with("T1")


def test_extract_slack_tokens_command_missing_profile(settings, tmp_path):
    settings.CHROME_PROFILE_PATH = str(tmp_path / "missing_profile")
    with pytest.raises(CommandError, match="Chrome profile not found"):
        call_command("extract_slack_tokens", "--team-id=T21Q22G66")
