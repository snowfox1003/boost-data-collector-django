"""
Workspace utilities - path helpers for raw export JSON and per-server data.

Layout: workspace/discord_activity_tracker/
  - chrome_profile/            (session storage for exporter credentials)
  - discord_internal_tokens.json (session credentials, not .env)
  - _exporter_staging/         (temporary DiscordChatExporter output; cleared each run)
"""

from pathlib import Path

from django.conf import settings

from config.workspace import get_workspace_path

_APP_SLUG = "discord_activity_tracker"

# Pre-exported DiscordChatExporter JSON dropped here for DB import (see backfill command).
CPP_DISCUSSION_IMPORT_SUBDIR = "Discussion - c-cpp-discussion"
CHROME_PROFILE_DIRNAME = "chrome_profile"
DISCORD_INTERNAL_TOKENS_FILENAME = "discord_internal_tokens.json"


def get_workspace_root() -> Path:
    """Return workspace/discord_activity_tracker/."""
    return get_workspace_path(_APP_SLUG)


def get_chrome_profile_path() -> Path:
    """Session storage directory for Discord exporter credentials."""
    path = get_workspace_root() / CHROME_PROFILE_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_discord_internal_tokens_json_path() -> Path:
    """JSON file storing Discord session credentials."""
    return get_workspace_root() / DISCORD_INTERNAL_TOKENS_FILENAME


def get_cpp_discussion_import_dir() -> Path:
    """Return workspace/discord_activity_tracker/Discussion - c-cpp-discussion/ (creates if missing)."""
    path = get_workspace_root() / CPP_DISCUSSION_IMPORT_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_raw_dir() -> Path:
    """Return WORKSPACE_DIR/raw/discord_activity_tracker/ for archived JSON (Boost-style layout)."""
    path = Path(settings.WORKSPACE_DIR) / "raw" / _APP_SLUG
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_exporter_staging_dir() -> Path:
    """Temporary directory for DiscordChatExporter output before per-day archival."""
    path = get_workspace_root() / "_exporter_staging"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_channel_raw_dir(server_id: int, channel_id: int) -> Path:
    """Return raw/discord_activity_tracker/<server_id>/<channel_id>/ for saved exports."""
    path = get_raw_dir() / str(server_id) / str(channel_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def clear_exporter_staging_dir() -> None:
    """Remove all files and subdirectories under the exporter staging directory."""
    import shutil

    staging = get_exporter_staging_dir()
    for child in staging.iterdir():
        if child.is_file():
            child.unlink(missing_ok=True)
        elif child.is_dir():
            shutil.rmtree(child, ignore_errors=True)


def get_server_dir(server_id: int) -> Path:
    """Return workspace/discord_activity_tracker/<server_id>/ (creates if needed)."""
    path = get_workspace_root() / str(server_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_channel_json_path(server_id: int, channel_id: int) -> Path:
    """Path for <server_id>/channels/<channel_id>.json"""
    path = get_server_dir(server_id) / "channels"
    path.mkdir(parents=True, exist_ok=True)
    return path / f"{channel_id}.json"


def get_messages_json_path(server_id: int, channel_id: int, date_str: str) -> Path:
    """Path for <server_id>/messages/<channel_id>/<YYYY-MM-DD>.json"""
    path = get_server_dir(server_id) / "messages" / str(channel_id)
    path.mkdir(parents=True, exist_ok=True)
    return path / f"{date_str}.json"


def iter_existing_message_jsons(server_id: int, channel_id: int):
    """Yield paths for messages/<channel_id>/*.json"""
    messages_dir = get_server_dir(server_id) / "messages" / str(channel_id)
    if not messages_dir.is_dir():
        return
    for path in sorted(messages_dir.glob("*.json")):
        if path.name.startswith("._"):
            continue
        yield path
