"""
Workspace paths for slack_event_handler.

Layout: workspace/slack_event_handler/
  - data/                      (state.json, raw event files)
  - chrome_profile/            (Slack login session for xoxc/xoxd extraction)
  - slack_internal_tokens.json (xoxc/xoxd tokens, not .env)
"""

import os
from pathlib import Path

from config.workspace import get_workspace_path

_APP_SLUG = "slack_event_handler"
CHROME_PROFILE_DIRNAME = "chrome_profile"
SLACK_INTERNAL_TOKENS_FILENAME = "slack_internal_tokens.json"


def get_workspace_root() -> Path:
    """Return this app's workspace directory (e.g. workspace/slack_event_handler/)."""
    return get_workspace_path(_APP_SLUG)


def get_data_dir() -> Path:
    """Return workspace/slack_event_handler/data/; creates if missing."""
    path = get_workspace_root() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_chrome_profile_path() -> Path:
    """Chrome user-data dir for Slack session extraction."""
    path = get_workspace_root() / CHROME_PROFILE_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_slack_internal_tokens_json_path() -> Path:
    """JSON file storing xoxc/xoxd per team."""
    return get_workspace_root() / SLACK_INTERNAL_TOKENS_FILENAME


def set_working_directory() -> None:
    """Change current working directory to this app's workspace root (for runner)."""
    root = get_workspace_root()
    os.chdir(root)
