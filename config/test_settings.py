"""
Test-only Django settings.
Imports base settings, then overrides for isolated tests.

Tests always use PostgreSQL (same as CI and production) so behavior matches
JSONB, case-sensitive ILIKE, connection pooling, and transaction semantics.
SQLite is not used: it can hide bugs that only appear on Postgres.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F401, F403
from .settings import DATABASES  # explicit import for ruff F405 (after star import)

# Never run workspace orphan cleanup during tests (CoreConfig.ready).
WORKSPACE_ORPHAN_CLEANUP_ENABLED = False

if not (os.environ.get("DATABASE_URL") or "").strip():
    raise ImproperlyConfigured(
        "config.test_settings requires DATABASE_URL (PostgreSQL). "
        "Start the local test database: "
        "docker compose -f docker-compose.test.yml up -d "
        "then set DATABASE_URL, for example: "
        "postgres://postgres:postgres@127.0.0.1:5433/postgres "
        "See README.md → Running tests."
    )

# Prefer short-lived connections and a bounded connect timeout so flaky
# networking fails fast instead of hanging pytest.
_default_db = DATABASES.get("default", {})
_engine = (_default_db.get("ENGINE") or "").lower()
if "postgresql" not in _engine:
    raise ImproperlyConfigured(
        "config.test_settings requires PostgreSQL. "
        f"Got DATABASES['default']['ENGINE']={_default_db.get('ENGINE')!r}; "
        "use a postgres:// or postgresql:// DATABASE_URL. "
        "See README.md → Running tests."
    )
_opts = dict(_default_db.get("OPTIONS") or {})
_opts.setdefault("connect_timeout", 15)
_default_db["OPTIONS"] = _opts
_default_db["CONN_MAX_AGE"] = 0
DATABASES["default"] = _default_db

# Tests assert production freshness rules; ignore .env HEALTH_ENFORCE_COLLECTOR_FRESHNESS=false
# used for local Docker / compose-smoke before collectors have run.
HEALTH_ENFORCE_COLLECTOR_FRESHNESS = True

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "{levelname} {message}", "style": "{"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
}

BASE_DIR = Path(__file__).resolve().parent.parent
_test_dir = BASE_DIR / ".test_artifacts"
_test_dir.mkdir(exist_ok=True)
WORKSPACE_DIR = _test_dir / "workspace"
WORKSPACE_DIR.mkdir(exist_ok=True)
for _slug in (
    "github_activity_tracker",
    "boost_library_tracker",
    "clang_github_tracker",
    "discord_activity_tracker",
    "reddit_activity_tracker",
    "shared",
):
    (WORKSPACE_DIR / _slug).mkdir(parents=True, exist_ok=True)
# Base settings computed DISCORD_CONTEXT_REPO_PATH before WORKSPACE_DIR was overridden above.
DISCORD_CONTEXT_REPO_PATH = (
    WORKSPACE_DIR / "discord_activity_tracker" / "discord-cplusplus-together-context"
).resolve()
LOG_DIR = _test_dir / "logs"
LOG_DIR.mkdir(exist_ok=True)

GITHUB_TOKEN = ""
GITHUB_TOKENS_SCRAPING = []
GITHUB_TOKEN_WRITE = ""

# Clang GitHub Tracker (tests use defaults)
CLANG_GITHUB_OWNER = "llvm"
CLANG_GITHUB_REPO = "llvm-project"
# Do not inherit publish target from developer .env (avoids real git / token in tests).
CLANG_GITHUB_CONTEXT_REPO_OWNER = ""
CLANG_GITHUB_CONTEXT_REPO_NAME = ""
CLANG_GITHUB_CONTEXT_REPO_BRANCH = ""

# Tests patch a single subprocess.Popen for DiscordChatExporter.
DISCORD_CHAT_EXPORTER_SEQUENTIAL_EXPORT = False

# Tests set DISCORD_USER_TOKEN via monkeypatch; do not inherit internal-token mode
# from developer .env (get_or_load_discord_user_token would ignore env token).
ALLOW_INTERNAL_DISCORD_TOKENS = False
DISCORD_USER_TOKEN = ""
