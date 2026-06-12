"""Discord session credential helpers for DiscordChatExporter flows."""

from __future__ import annotations

import logging
import re
import shutil
import tempfile
from pathlib import Path

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

DISCORD_USERS_ME_URL = "https://discord.com/api/v9/users/@me"

# Local storage keys for Discord session credentials.
DISCORD_TOKEN_KEY = b"_https://discord.com\x00\x01token"
DISCORD_TOKEN_KEY_LEGACY = b"_https://discordapp.com\x00\x01token"
DISCORD_TOKEN_MARKER = b"\x01token"

CHROME_PROFILE_PATH_PATTERN = re.compile(r"^[a-zA-Z0-9/_. \-:]+$")

# Substrings in DiscordChatExporter stderr that indicate auth failure.
DISCORD_EXPORTER_AUTH_MARKERS = (
    "401",
    "403",
    "unauthorized",
    "Unauthorized",
    "invalid token",
    "Invalid token",
    "not authorized",
    "Not authorized",
)


def _validate_chrome_profile_path(path: str) -> str:
    """Validate DISCORD_CHROME_PROFILE_PATH format. Raises ValueError if invalid."""
    if not path or not isinstance(path, str):
        raise ValueError("DISCORD_CHROME_PROFILE_PATH must be a non-empty string")
    path = path.strip()
    if "\x00" in path:
        raise ValueError("DISCORD_CHROME_PROFILE_PATH must not contain null bytes")
    normalized = Path(path).as_posix()
    if not CHROME_PROFILE_PATH_PATTERN.match(normalized):
        raise ValueError(
            "DISCORD_CHROME_PROFILE_PATH must contain only path characters "
            "(letters, digits, /, _, ., -, space, :), got: %s" % (path[:100],)
        )
    return path


def _resolve_discord_chrome_profile_root() -> Path:
    """Return validated session storage directory for Discord credentials."""
    from discord_activity_tracker.workspace import get_chrome_profile_path

    raw = (getattr(settings, "DISCORD_CHROME_PROFILE_PATH", "") or "").strip()
    if not raw:
        return get_chrome_profile_path()
    validated = _validate_chrome_profile_path(raw)
    root = Path(validated).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    return root.resolve()


def _leveldb_path(profile_root: Path) -> Path:
    return profile_root / "Default" / "Local Storage" / "leveldb"


def _parse_discord_token_raw(raw: bytes) -> str:
    """Parse credential value from local storage (strip prefix byte + JSON quotes)."""
    if not raw:
        raise ValueError("Discord token value is empty")
    if raw[0:1] in (b"\x00", b"\x01"):
        text = raw[1:].decode("utf-8", errors="replace")
    else:
        text = raw.decode("utf-8", errors="replace")
    text = text.strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1]
    token = text.strip()
    if not token:
        raise ValueError("Discord token value is empty after parsing")
    return token


def _read_leveldb_value(leveldb_dir: Path, key: bytes) -> bytes | None:
    """Read a single key from local storage; copy to temp dir if locked."""
    try:
        import plyvel
    except ImportError:
        logger.warning(
            "plyvel is not installed; cannot read session storage at %s. "
            "See .env.example for supported environments.",
            leveldb_dir,
        )
        return None

    keys_to_try = (key,)

    def _get_from_db(db_path: str) -> bytes | None:
        db = plyvel.DB(db_path, create_if_missing=False)
        try:
            for k in keys_to_try:
                value = db.get(k)
                if value is not None:
                    return value
            for db_key, db_value in db.iterator():
                if DISCORD_TOKEN_MARKER in db_key and db_key.endswith(b"token"):
                    return db_value
            return None
        finally:
            db.close()

    try:
        return _get_from_db(str(leveldb_dir))
    except plyvel.Error as e:
        err = str(e).lower()
        if "lock" not in err and "resource temporarily unavailable" not in err:
            raise
        logger.debug("LevelDB locked at %s, copying to temp dir", leveldb_dir)
        with tempfile.TemporaryDirectory(prefix="leveldb-") as tmp:
            shutil.copytree(leveldb_dir, Path(tmp) / "leveldb", dirs_exist_ok=True)
            return _get_from_db(str(Path(tmp) / "leveldb"))


def _read_discord_token_from_leveldb(profile_root: Path) -> str | None:
    """Load Discord credential from configured session storage."""
    leveldb_dir = _leveldb_path(profile_root)
    if not leveldb_dir.is_dir():
        logger.warning("LevelDB not found at %s", leveldb_dir)
        return None
    for key in (DISCORD_TOKEN_KEY, DISCORD_TOKEN_KEY_LEGACY):
        try:
            raw = _read_leveldb_value(leveldb_dir, key)
            if raw:
                return _parse_discord_token_raw(raw)
        except ValueError as e:
            logger.warning(
                "Error parsing Discord credential from session storage: %s", e
            )
            continue
        except Exception as e:
            logger.warning(
                "Error reading Discord credential from session storage: %s", e
            )
            continue
    logger.warning("Discord credential not found in %s", leveldb_dir)
    return None


def probe_discord_user_token(token: str) -> bool:
    """Return True if credential authenticates against Discord GET /users/@me."""
    token = (token or "").strip()
    if not token:
        return False
    try:
        response = requests.get(
            DISCORD_USERS_ME_URL,
            headers={"Authorization": token},
            timeout=30,
        )
        if response.status_code == 200:
            return True
        if response.status_code in (401, 403):
            logger.debug(
                "Discord token probe auth error: HTTP %s", response.status_code
            )
            return False
        logger.debug(
            "Discord token probe unexpected status %s (treating as invalid)",
            response.status_code,
        )
        return False
    except Exception as e:
        logger.debug("Discord token probe request failed: %s", e)
        return False


def probe_discord_user_token_details(token: str) -> dict | None:
    """Return user details from GET /users/@me when credential is valid, else None."""
    token = (token or "").strip()
    if not token:
        return None
    try:
        response = requests.get(
            DISCORD_USERS_ME_URL,
            headers={"Authorization": token},
            timeout=30,
        )
        if response.status_code != 200:
            return None
        data = response.json()
        if not isinstance(data, dict):
            return None
        user_id = str(data.get("id") or "").strip()
        username = str(data.get("username") or "").strip()
        out: dict[str, str] = {}
        if user_id:
            out["user_id"] = user_id
        if username:
            out["username"] = username
        return out or None
    except Exception as e:
        logger.debug("Discord token probe details failed: %s", e)
        return None


def is_discord_exporter_auth_error(message: str) -> bool:
    """True if DiscordChatExporter stderr/message indicates auth failure."""
    text = (message or "").lower()
    if not text:
        return False
    if "401" in message or "403" in message:
        return True
    for marker in DISCORD_EXPORTER_AUTH_MARKERS:
        if marker.lower() in text:
            return True
    return False


def extract_discord_token_auto() -> dict | None:
    """Load Discord session credentials from configured workspace paths."""
    logger.debug("Loading Discord session credentials")
    try:
        profile_root = _resolve_discord_chrome_profile_root()
    except ValueError as e:
        logger.error("%s", e)
        return None
    if not profile_root.is_dir():
        logger.error(
            "Session storage not found at %s. See .env.example.",
            profile_root,
        )
        return None
    user_token = _read_discord_token_from_leveldb(profile_root)
    if not user_token:
        logger.error(
            "Failed to read Discord credentials from workspace storage. See .env.example."
        )
        return None
    if not probe_discord_user_token(user_token):
        logger.error(
            "Discord credentials failed auth probe. Session may be expired or invalid."
        )
        return None
    result: dict[str, str] = {"user_token": user_token}
    details = probe_discord_user_token_details(user_token)
    if details:
        result.update(details)
    return result
