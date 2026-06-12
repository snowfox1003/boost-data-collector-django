"""Persist Slack session credentials as JSON under workspace/slack_event_handler/."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from django.conf import settings

from slack_event_handler.workspace import get_slack_internal_tokens_json_path

logger = logging.getLogger(__name__)

SLACK_TOKENS_RELOGIN_HINT = "Session credentials invalid or unavailable. Check workspace configuration per .env.example."


def slack_internal_tokens_json_path() -> Path:
    """Resolved path to the tokens JSON file."""
    override = (getattr(settings, "SLACK_INTERNAL_TOKENS_JSON", "") or "").strip()
    if override:
        path = Path(override).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        return path.resolve()
    return get_slack_internal_tokens_json_path().resolve()


def _read_document(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"teams": {}}
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return {"teams": {}}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid tokens file (expected object): {path}")
    teams = data.get("teams")
    if teams is None:
        data["teams"] = {}
    elif not isinstance(teams, dict):
        raise ValueError(f"Invalid tokens file (teams must be object): {path}")
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
    logger.debug("Saved Slack internal tokens to %s", path)


def save_slack_internal_tokens(
    team_id: str,
    xoxc: str,
    xoxd: str,
    *,
    team_name: str | None = None,
    user_id: str | None = None,
) -> Path:
    """Write session credentials for team_id into workspace JSON. Returns path written."""
    team_id = (team_id or "").strip()
    xoxc = (xoxc or "").strip()
    xoxd = (xoxd or "").strip()
    if not team_id or not xoxc or not xoxd:
        raise ValueError("team_id, xoxc, and xoxd are required")

    path = slack_internal_tokens_json_path()
    doc = _read_document(path)
    entry: dict[str, Any] = {
        "xoxc": xoxc,
        "xoxd": xoxd,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if team_name:
        entry["team_name"] = team_name
    if user_id:
        entry["user_id"] = user_id
    doc["teams"][team_id] = entry
    _write_document(path, doc)
    return path


def load_slack_internal_tokens(team_id: str) -> dict[str, str] | None:
    """Load token record for team_id, or None if missing."""
    team_id = (team_id or "").strip()
    if not team_id:
        return None
    path = slack_internal_tokens_json_path()
    try:
        doc = _read_document(path)
    except (OSError, json.JSONDecodeError, ValueError) as e:
        logger.warning("Could not read Slack internal tokens from %s: %s", path, e)
        return None
    entry = doc.get("teams", {}).get(team_id)
    if not isinstance(entry, dict):
        return None
    xoxc = (entry.get("xoxc") or "").strip()
    xoxd = (entry.get("xoxd") or "").strip()
    if not xoxc or not xoxd:
        return None
    out = {"xoxc": xoxc, "xoxd": xoxd, "team_id": team_id}
    if entry.get("team_name"):
        out["team_name"] = str(entry["team_name"])
    if entry.get("user_id"):
        out["user_id"] = str(entry["user_id"])
    return out


def extract_and_save_slack_internal_tokens(team_id: str) -> tuple[str, str] | None:
    """Load session credentials from workspace storage and persist to workspace JSON."""
    from slack_event_handler.utils.slack_tokens import extract_slack_tokens_auto

    tokens = extract_slack_tokens_auto(team_id)
    if not tokens or "xoxc" not in tokens or "xoxd" not in tokens:
        return None
    save_slack_internal_tokens(
        team_id,
        tokens["xoxc"],
        tokens["xoxd"],
        team_name=tokens.get("team_name"),
        user_id=tokens.get("user_id"),
    )
    return tokens["xoxc"], tokens["xoxd"]


def get_slack_internal_token_pair(team_id: str | None = None) -> tuple[str, str] | None:
    """Return session credential pair from workspace JSON when internal mode is enabled."""
    allow = getattr(settings, "ALLOW_INTERNAL_SLACK_TOKENS", False)
    if isinstance(allow, str):
        allow = allow.strip().lower() == "true"
    if not allow:
        return None

    tid = (team_id or "").strip()
    if not tid:
        from core.operations.slack_ops.tokens import get_default_team_key

        tid = (get_default_team_key() or "").strip()
    if not tid:
        return None

    record = load_slack_internal_tokens(tid)
    if not record:
        return None
    return record["xoxc"], record["xoxd"]


def _resolve_team_id(team_id: str | None = None) -> str:
    tid = (team_id or "").strip()
    if not tid:
        from core.operations.slack_ops.tokens import get_default_team_key

        tid = (get_default_team_key() or "").strip()
    return tid


def log_slack_internal_tokens_still_invalid(team_id: str) -> None:
    """Log when session credentials remain invalid after refresh."""
    logger.error(
        "Slack session credentials still invalid for team %s. %s",
        team_id,
        SLACK_TOKENS_RELOGIN_HINT,
    )


def log_slack_internal_tokens_extract_failed(team_id: str) -> None:
    """Log when session credentials could not be loaded from workspace storage."""
    logger.error(
        "Failed to load Slack session credentials for team %s. %s",
        team_id,
        SLACK_TOKENS_RELOGIN_HINT,
    )


def _extract_validate_and_return(team_id: str) -> tuple[str, str] | None:
    """Refresh credentials from workspace storage; return pair only if auth probe passes."""
    from slack_event_handler.utils.slack_tokens import probe_slack_internal_tokens

    pair = extract_and_save_slack_internal_tokens(team_id)
    if not pair:
        log_slack_internal_tokens_extract_failed(team_id)
        return None
    if probe_slack_internal_tokens(pair[0], pair[1]):
        return pair
    log_slack_internal_tokens_still_invalid(team_id)
    return None


def get_or_load_slack_internal_token_pair(
    team_id: str | None = None,
) -> tuple[str, str] | None:
    """
    Return session credential pair from workspace JSON.

    Refreshes from workspace storage when JSON is missing or credentials fail auth probe.
    Returns None if credentials remain invalid.
    """
    from slack_event_handler.utils.slack_tokens import probe_slack_internal_tokens

    tid = _resolve_team_id(team_id)
    if not tid:
        return None

    allow = getattr(settings, "ALLOW_INTERNAL_SLACK_TOKENS", False)
    if isinstance(allow, str):
        allow = allow.strip().lower() == "true"
    if not allow:
        return None

    pair = get_slack_internal_token_pair(tid)
    if pair:
        if probe_slack_internal_tokens(pair[0], pair[1]):
            return pair
        logger.info(
            "Slack session credentials in JSON are stale for team %s; refreshing",
            tid,
        )
        return _extract_validate_and_return(tid)

    logger.info(
        "Slack session credentials not in JSON; loading for team %s",
        tid,
    )
    return _extract_validate_and_return(tid)
