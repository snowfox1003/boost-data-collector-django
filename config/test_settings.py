"""
Test-only Django settings.
Imports base settings, then overrides for fast and isolated tests.
"""

import os
import sys
from pathlib import Path

from .settings import *  # noqa: F401, F403

# In-memory SQLite for fast, isolated tests when we are not targeting Postgres (see below).
_SQLITE_TEST_DB = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Prefer SQLite when DATABASE_URL is unset, or under pytest without USE_POSTGRES_TESTS so a
# developer .env DATABASE_URL (Docker Postgres) does not require a running server.
# GitHub Actions Postgres jobs set USE_POSTGRES_TESTS=1 so DATABASE_URL still applies under pytest.
_under_pytest = "pytest" in sys.modules
_use_postgres_tests = os.environ.get("USE_POSTGRES_TESTS", "").strip().lower() in (
    "1",
    "true",
    "yes",
)
_want_sqlite = (not os.environ.get("DATABASE_URL", "").strip()) or (
    _under_pytest and not _use_postgres_tests
)
if _want_sqlite:
    DATABASES = _SQLITE_TEST_DB

# When tests target PostgreSQL (e.g. CI), prefer short-lived connections and a bounded
# connect timeout so flaky networking fails fast instead of hanging pytest.
_default_db = DATABASES.get("default", {})
if "postgresql" in (_default_db.get("ENGINE") or "").lower():
    _opts = dict(_default_db.get("OPTIONS") or {})
    _opts.setdefault("connect_timeout", 15)
    _default_db["OPTIONS"] = _opts
    _default_db["CONN_MAX_AGE"] = 0
    DATABASES["default"] = _default_db

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
    "shared",
):
    (WORKSPACE_DIR / _slug).mkdir(parents=True, exist_ok=True)
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
