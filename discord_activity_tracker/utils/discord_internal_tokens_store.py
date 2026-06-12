"""Persist Discord session credentials as JSON under workspace/discord_activity_tracker/."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from django.conf import settings

from discord_activity_tracker.workspace import get_discord_internal_tokens_json_path

logger = logging.getLogger(__name__)

DISCORD_TOKENS_RELOGIN_HINT = "Session credentials invalid or unavailable. Check workspace configuration per .env.example."


def discord_internal_tokens_json_path() -> Path:
    """Resolved path to the tokens JSON file."""
    override = (getattr(settings, "DISCORD_INTERNAL_TOKENS_JSON", "") or "").strip()
    if override:
        path = Path(override).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        return path.resolve()
    return get_discord_internal_tokens_json_path().resolve()


def _read_document(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid tokens file (expected object): {path}")
    return data


def _write_document(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    payload = json.dumps(data, indent=2, sort_keys=True)
    tmp.write_text(payload + "\n", encoding="utf-8")
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    logger.debug("Saved Discord session credentials to %s", path)


def save_discord_internal_tokens(
    user_token: str,
    *,
    user_id: str | None = None,
    username: str | None = None,
) -> Path:
    """Write session credential into workspace JSON. Returns path written."""
    user_token = (user_token or "").strip()
    if not user_token:
        raise ValueError("user_token is required")

    path = discord_internal_tokens_json_path()
    entry: dict[str, Any] = {
        "user_token": user_token,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if user_id:
        entry["user_id"] = user_id
    if username:
        entry["username"] = username
    _write_document(path, entry)
    return path


def load_discord_internal_tokens() -> dict[str, str] | None:
    """Load credential record, or None if missing."""
    path = discord_internal_tokens_json_path()
    try:
        doc = _read_document(path)
    except (OSError, json.JSONDecodeError, ValueError) as e:
        logger.warning(
            "Could not read Discord session credentials from %s: %s", path, e
        )
        return None
    user_token = (doc.get("user_token") or "").strip()
    if not user_token:
        return None
    out: dict[str, str] = {"user_token": user_token}
    if doc.get("user_id"):
        out["user_id"] = str(doc["user_id"])
    if doc.get("username"):
        out["username"] = str(doc["username"])
    return out


def extract_and_save_discord_internal_tokens() -> str | None:
    """Load credentials from workspace storage and persist to workspace JSON."""
    from discord_activity_tracker.utils.discord_tokens import extract_discord_token_auto

    tokens = extract_discord_token_auto()
    if not tokens or "user_token" not in tokens:
        return None
    save_discord_internal_tokens(
        tokens["user_token"],
        user_id=tokens.get("user_id"),
        username=tokens.get("username"),
    )
    return tokens["user_token"]


def _allow_internal_discord_tokens() -> bool:
    allow = getattr(settings, "ALLOW_INTERNAL_DISCORD_TOKENS", False)
    if isinstance(allow, str):
        return allow.strip().lower() == "true"
    return bool(allow)


def get_discord_user_token_from_json() -> str | None:
    """Return session credential from workspace JSON when internal mode is enabled."""
    if not _allow_internal_discord_tokens():
        return None
    record = load_discord_internal_tokens()
    if not record:
        return None
    return record["user_token"]


def log_discord_internal_tokens_still_invalid() -> None:
    """Log when session credentials remain invalid after refresh."""
    logger.error(
        "Discord session credentials still invalid. %s",
        DISCORD_TOKENS_RELOGIN_HINT,
    )


def log_discord_internal_tokens_extract_failed() -> None:
    """Log when session credentials could not be loaded from workspace storage."""
    logger.error(
        "Failed to load Discord session credentials. %s",
        DISCORD_TOKENS_RELOGIN_HINT,
    )


def _extract_validate_and_return() -> str | None:
    """Refresh credentials from workspace storage; return token only if auth probe passes."""
    from discord_activity_tracker.utils.discord_tokens import probe_discord_user_token

    token = extract_and_save_discord_internal_tokens()
    if not token:
        log_discord_internal_tokens_extract_failed()
        return None
    if probe_discord_user_token(token):
        return token
    log_discord_internal_tokens_still_invalid()
    return None


def get_or_load_discord_user_token() -> str | None:
    """
    Return Discord credential for DiscordChatExporter.

    Reads workspace JSON when internal mode is enabled and refreshes when stale.
    Otherwise returns credential from settings (.env).
    """
    if not _allow_internal_discord_tokens():
        return (getattr(settings, "DISCORD_USER_TOKEN", "") or "").strip() or None

    from discord_activity_tracker.utils.discord_tokens import probe_discord_user_token

    token = get_discord_user_token_from_json()
    if token:
        if probe_discord_user_token(token):
            return token
        logger.info("Discord session credentials in JSON are stale; refreshing")
        return _extract_validate_and_return()

    logger.info(
        "Discord session credentials not in JSON; loading from workspace storage"
    )
    return _extract_validate_and_return()
