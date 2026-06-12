"""Slack session credential helpers for huddle transcript flows."""

import json
import logging
import re
import shutil
import tempfile
from pathlib import Path

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# Slack files.info errors that indicate stale session credentials (not missing file).
SLACK_INTERNAL_TOKEN_AUTH_ERRORS = frozenset(
    {
        "invalid_auth",
        "not_authed",
        "token_expired",
        "token_revoked",
        "invalid_cookie",
        "account_inactive",
    }
)

# Dummy file id for auth probe; file_not_found means auth succeeded.
SLACK_TOKEN_PROBE_FILE_ID = "F00000000000"

# Chromium localStorage key for Slack app (https://app.slack.com)
LOCAL_CONFIG_V2_KEY = b"_https://app.slack.com\x00\x01localConfig_v2"
LOCAL_CONFIG_V2_MARKER = b"localConfig_v2"

# Session storage path: validate normalized POSIX form (Windows drive letters via ":").
CHROME_PROFILE_PATH_PATTERN = re.compile(r"^[a-zA-Z0-9/_. \-:]+$")


def _validate_chrome_profile_path(path: str) -> str:
    """Validate CHROME_PROFILE_PATH format. Raises ValueError if invalid."""
    if not path or not isinstance(path, str):
        raise ValueError("CHROME_PROFILE_PATH must be a non-empty string")
    path = path.strip()
    if "\x00" in path:
        raise ValueError("CHROME_PROFILE_PATH must not contain null bytes")
    normalized = Path(path).as_posix()
    if not CHROME_PROFILE_PATH_PATTERN.match(normalized):
        raise ValueError(
            "CHROME_PROFILE_PATH must contain only path characters (letters, digits, /, _, ., -, space, :), got: %s"
            % (path[:100],)
        )
    return path


def _resolve_chrome_profile_root() -> Path:
    """Return validated session storage directory for Slack credentials."""
    from slack_event_handler.workspace import get_chrome_profile_path

    raw = (getattr(settings, "CHROME_PROFILE_PATH", "") or "").strip()
    if not raw:
        return get_chrome_profile_path()
    validated = _validate_chrome_profile_path(raw)
    root = Path(validated).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    return root.resolve()


def _leveldb_path(profile_root: Path) -> Path:
    return profile_root / "Default" / "Local Storage" / "leveldb"


def _cookies_path(profile_root: Path) -> Path:
    return profile_root / "Default" / "Cookies"


def _parse_local_config_raw(raw: bytes) -> dict:
    """Parse localConfig_v2 payload (strip optional prefix byte)."""
    if not raw:
        raise ValueError("localConfig_v2 is empty")
    if raw[0:1] in (b"\x00", b"\x01"):
        text = raw[1:].decode("utf-8", errors="replace")
    else:
        text = raw.decode("utf-8", errors="replace")
    return json.loads(text)


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

    try:
        db = plyvel.DB(str(leveldb_dir), create_if_missing=False)
        try:
            value = db.get(key)
            if value is not None:
                return value
            for db_key, db_value in db.iterator():
                if LOCAL_CONFIG_V2_MARKER in db_key:
                    return db_value
            return None
        finally:
            db.close()
    except plyvel.Error as e:
        err = str(e).lower()
        if "lock" not in err and "resource temporarily unavailable" not in err:
            raise
        logger.debug("LevelDB locked at %s, copying to temp dir", leveldb_dir)
        with tempfile.TemporaryDirectory(prefix="leveldb-") as tmp:
            shutil.copytree(leveldb_dir, Path(tmp) / "leveldb", dirs_exist_ok=True)
            db = plyvel.DB(str(Path(tmp) / "leveldb"), create_if_missing=False)
            try:
                value = db.get(key)
                if value is not None:
                    return value
                for db_key, db_value in db.iterator():
                    if LOCAL_CONFIG_V2_MARKER in db_key:
                        return db_value
                return None
            finally:
                db.close()


def _read_local_config_v2(profile_root: Path) -> dict | None:
    """Load and parse localConfig_v2 from session storage."""
    leveldb_dir = _leveldb_path(profile_root)
    if not leveldb_dir.is_dir():
        logger.warning("LevelDB not found at %s", leveldb_dir)
        return None
    try:
        raw = _read_leveldb_value(leveldb_dir, LOCAL_CONFIG_V2_KEY)
        if not raw:
            logger.warning("localConfig_v2 not found in %s", leveldb_dir)
            return None
        return _parse_local_config_raw(raw)
    except json.JSONDecodeError as e:
        logger.warning("Error parsing localConfig_v2 JSON: %s", e)
        return None
    except Exception as e:
        logger.warning("Error reading localConfig_v2: %s", e)
        return None


def _chrome_linux_v10_cookie_key() -> bytes:
    """AES key for Chromium v10 encrypted session values on Linux."""
    from Cryptodome.Protocol.KDF import PBKDF2

    return PBKDF2(b"peanuts", b"saltysalt", dkLen=16, count=1)


def _decrypt_chrome_linux_v10_cookie(encrypted_value: bytes) -> str:
    """Decrypt Chromium v10 encrypted session blobs (AES-128-CBC)."""
    if not encrypted_value.startswith(b"v10"):
        raise ValueError("unsupported Chrome cookie encryption (expected v10 prefix)")
    from Cryptodome.Cipher import AES

    cipher = AES.new(_chrome_linux_v10_cookie_key(), AES.MODE_CBC, iv=b" " * 16)
    plain = cipher.decrypt(encrypted_value[3:])
    pad = plain[-1]
    if pad < 1 or pad > 16 or plain[-pad:] != bytes([pad]) * pad:
        raise ValueError("invalid Chrome cookie padding")
    return plain[32:-pad].decode("utf-8")


def _read_xoxd_cookie_from_sqlite(cookies_file: Path) -> str | None:
    """Read session value from SQLite storage with Linux v10 decryption."""
    import sqlite3

    conn = sqlite3.connect(f"file:{cookies_file}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            """
            SELECT encrypted_value FROM cookies
            WHERE name = 'd' AND (host_key LIKE '%slack.com' OR host_key = '.slack.com')
            ORDER BY length(encrypted_value) DESC
            """
        ).fetchall()
    finally:
        conn.close()
    for (encrypted_value,) in rows:
        if not encrypted_value:
            continue
        try:
            value = _decrypt_chrome_linux_v10_cookie(encrypted_value)
            if value:
                return value
        except Exception as e:
            logger.debug("Could not decrypt cookie row: %s", e)
    return None


def _read_xoxd_cookie(profile_root: Path) -> str | None:
    """Read secondary session credential from configured storage."""
    cookies_file = _cookies_path(profile_root)
    if not cookies_file.is_file():
        logger.warning("Session storage database not found at %s", cookies_file)
        return None
    try:
        import browser_cookie3

        jar = browser_cookie3.chrome(
            cookie_file=str(cookies_file),
            domain_name="slack.com",
        )
        for cookie in jar:
            if cookie.name == "d" and cookie.value:
                return cookie.value
    except Exception as e:
        logger.debug("browser_cookie3 could not read cookie 'd': %s", e)

    try:
        value = _read_xoxd_cookie_from_sqlite(cookies_file)
        if value:
            return value
    except Exception as e:
        logger.warning("Error reading session credential from SQLite: %s", e)
        return None

    logger.warning("Secondary session credential not found in %s", cookies_file)
    return None


def extract_slack_tokens_from_config(
    local_config: dict, xoxd: str, team_id: str
) -> dict | None:
    """Build session credential dict from parsed localConfig, or None."""
    try:
        teams = local_config.get("teams", {})
        team_data = teams.get(team_id)
        if not team_data:
            logger.warning(
                "Team ID '%s' not found in localConfig_v2. Available: %s",
                team_id,
                list(teams.keys()),
            )
            return None
        xoxc_token = team_data.get("token")
        team_name = team_data.get("name")
        user_id = team_data.get("user_id")
        if not xoxc_token:
            logger.warning("Primary session credential not found in team data")
            return None
        if not xoxd:
            logger.warning("Secondary session credential not found")
            return None
        tokens = {
            "xoxc": xoxc_token,
            "xoxd": xoxd,
            "team_id": team_id,
            "team_name": team_name,
            "user_id": user_id,
        }
        logger.debug("Session credentials loaded for team %s", team_name)
        return tokens
    except Exception as e:
        logger.warning("Error loading session credentials: %s", e)
        return None


def get_all_team_ids_from_config(local_config: dict) -> list[str]:
    """Get all available team IDs from parsed localConfig."""
    try:
        teams = local_config.get("teams", {})
        return list(teams.keys())
    except Exception as e:
        logger.warning("Error getting team IDs: %s", e)
        return []


def get_all_team_ids(local_config: dict | None = None) -> list[str]:
    """Get team IDs from localConfig; reads workspace storage if not provided."""
    if local_config is not None:
        return get_all_team_ids_from_config(local_config)
    try:
        profile_root = _resolve_chrome_profile_root()
        config = _read_local_config_v2(profile_root)
        if not config:
            return []
        return get_all_team_ids_from_config(config)
    except ValueError as e:
        logger.warning("%s", e)
        return []


def is_slack_internal_token_auth_error(error: str | None) -> bool:
    """True if Slack API error indicates expired or invalid session credentials."""
    return (error or "").strip() in SLACK_INTERNAL_TOKEN_AUTH_ERRORS


def probe_slack_internal_tokens(
    xoxc: str,
    xoxd: str,
    file_id: str = SLACK_TOKEN_PROBE_FILE_ID,
) -> bool:
    """Return True if session credentials authenticate against Slack files.info."""
    xoxc = (xoxc or "").strip()
    xoxd = (xoxd or "").strip()
    if not xoxc or not xoxd:
        return False
    try:
        response = requests.post(
            "https://slack.com/api/files.info",
            headers={"Authorization": f"Bearer {xoxc}"},
            cookies={"d": xoxd},
            data={"file": file_id, "include_transcription": "true"},
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()
    except Exception as e:
        logger.debug("Slack token probe request failed: %s", e)
        return False
    if result.get("ok"):
        return True
    err = (result.get("error") or "").strip()
    if is_slack_internal_token_auth_error(err):
        logger.debug("Slack token probe auth error: %s", err)
        return False
    logger.debug("Slack token probe non-auth response (tokens valid): %s", err)
    return True


def extract_slack_tokens_auto(team_id: str) -> dict | None:
    """Load session credentials for team_id from configured workspace paths."""
    logger.debug("Loading Slack session credentials for team %s", team_id)
    try:
        profile_root = _resolve_chrome_profile_root()
    except ValueError as e:
        logger.error("%s", e)
        return None
    if not profile_root.is_dir():
        logger.error(
            "Session storage not found at %s. See .env.example.",
            profile_root,
        )
        return None
    local_config = _read_local_config_v2(profile_root)
    if not local_config:
        logger.error(
            "Failed to read session configuration from workspace storage. See .env.example."
        )
        return None
    team_ids = get_all_team_ids_from_config(local_config)
    if team_ids:
        logger.debug("Available team IDs: %s", ", ".join(team_ids))
    xoxd = _read_xoxd_cookie(profile_root)
    if not xoxd:
        logger.error(
            "Failed to read secondary session credential from workspace storage."
        )
        return None
    logger.debug("Loading session credentials for team ID: %s", team_id)
    tokens = extract_slack_tokens_from_config(local_config, xoxd, team_id)
    if tokens:
        return tokens
    logger.warning("Failed to load session credentials for team %s", team_id)
    return None
