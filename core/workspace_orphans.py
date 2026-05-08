"""
Detect and clean orphan workspace files for github_activity_tracker JSON cache.

Phase 1: under workspace/github_activity_tracker/<owner>/<repo>/{commits,issues,prs}/*.json
- Empty or invalid JSON → partial write / corruption → remove or quarantine.
- Valid JSON older than optional threshold → log warning only (may be legitimate backlog).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

_GITHUB_APP_SLUG = "github_activity_tracker"
_CACHE_SUBDIRS = ("commits", "issues", "prs")
_QUARANTINE_SEG = "_quarantine"


@dataclass
class GithubJsonCleanupStats:
    scanned: int = 0
    removed_invalid: int = 0
    quarantined_invalid: int = 0
    skipped_grace_invalid: int = 0
    stale_valid_warnings: int = 0
    errors: int = 0


def iter_github_activity_tracker_cache_json_files(workspace_dir: Path):
    """
    Yield *.json paths under .../github_activity_tracker/<owner>/<repo>/{commits,issues,prs}/.
    Skips workspace/github_activity_tracker/clones/ and quarantine dirs.
    """
    gat = workspace_dir / _GITHUB_APP_SLUG
    if not gat.is_dir():
        return
    for owner_dir in sorted(gat.iterdir()):
        if not owner_dir.is_dir():
            continue
        name = owner_dir.name
        if name.startswith(".") or name == "clones":
            continue
        for repo_dir in sorted(owner_dir.iterdir()):
            if not repo_dir.is_dir():
                continue
            for sub in _CACHE_SUBDIRS:
                bucket = repo_dir / sub
                if not bucket.is_dir():
                    continue
                for path in sorted(bucket.glob("*.json")):
                    if _QUARANTINE_SEG in path.parts:
                        continue
                    yield path


def classify_json_file(path: Path) -> str:
    """
    Return 'empty', 'invalid', or 'valid'.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return "invalid"
    if size == 0:
        return "empty"
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return "invalid"
    try:
        json.loads(raw)
    except json.JSONDecodeError:
        return "invalid"
    return "valid"


def _quarantine_path(workspace_dir: Path, source: Path) -> Path:
    rel = source.relative_to(workspace_dir)
    dest = workspace_dir / _QUARANTINE_SEG / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    return dest


def cleanup_github_activity_tracker_json_cache(
    *,
    workspace_dir: Path,
    execute: bool,
    use_quarantine: bool,
    stale_max_age_seconds: float | None,
    invalid_grace_seconds: float | None = None,
) -> GithubJsonCleanupStats:
    """
    Remove or quarantine empty/invalid JSON; log warnings for valid JSON older than threshold.

    If execute is False, only log what would happen (dry-run for removals).

    invalid_grace_seconds: skip invalid/empty files newer than this (mtime age); avoids
    racing an in-flight writer. None uses django.conf.settings.WORKSPACE_ORPHAN_INVALID_JSON_GRACE_SECONDS.
    Use 0.0 to disable the grace window.
    """
    stats = GithubJsonCleanupStats()
    now = time.time()
    grace = invalid_grace_seconds
    if grace is None:
        grace = float(
            getattr(settings, "WORKSPACE_ORPHAN_INVALID_JSON_GRACE_SECONDS", 5.0)
        )

    for path in iter_github_activity_tracker_cache_json_files(workspace_dir):
        stats.scanned += 1
        kind = classify_json_file(path)
        if kind in ("empty", "invalid"):
            if grace > 0:
                try:
                    age = now - path.stat().st_mtime
                except FileNotFoundError:
                    logger.debug(
                        "Invalid JSON cache vanished before grace check (concurrent worker?): %s",
                        path,
                    )
                    continue
                except OSError as e:
                    stats.errors += 1
                    logger.warning(
                        "Could not stat github_activity_tracker cache for grace check %s: %s",
                        path,
                        e,
                    )
                    continue
                if age < grace:
                    stats.skipped_grace_invalid += 1
                    logger.debug(
                        "Skipping invalid/empty JSON cache (within grace %.1fs, age %.3fs): %s",
                        grace,
                        age,
                        path,
                    )
                    continue
            if not execute:
                logger.info(
                    "Would remove invalid github_activity_tracker cache JSON: %s",
                    path,
                )
                stats.removed_invalid += 1
                continue
            try:
                if use_quarantine:
                    dest = _quarantine_path(workspace_dir, path)
                    shutil.move(os.fspath(path), os.fspath(dest))
                    stats.quarantined_invalid += 1
                    logger.warning(
                        "Quarantined invalid/empty JSON cache file: %s -> %s",
                        path,
                        dest,
                    )
                else:
                    path.unlink()
                    stats.removed_invalid += 1
                    logger.warning(
                        "Removed invalid/empty JSON cache file: %s",
                        path,
                    )
            except FileNotFoundError:
                logger.debug(
                    "Invalid JSON cache already removed (concurrent worker?): %s",
                    path,
                )
            except OSError as e:
                stats.errors += 1
                logger.warning("Could not handle invalid JSON cache %s: %s", path, e)
            continue

        # valid JSON
        if stale_max_age_seconds is not None and stale_max_age_seconds > 0:
            try:
                age = now - path.stat().st_mtime
            except OSError:
                continue
            if age > stale_max_age_seconds:
                stats.stale_valid_warnings += 1
                logger.warning(
                    "Stale valid JSON cache file (age %.0fs > %.0fs): %s",
                    age,
                    stale_max_age_seconds,
                    path,
                )

    return stats


def run_startup_workspace_cleanup() -> None:
    """
    Called from CoreConfig.ready when WORKSPACE_ORPHAN_CLEANUP_ENABLED is True.
    Uses django settings for paths and behavior.
    """
    workspace_dir = Path(settings.WORKSPACE_DIR)
    use_quarantine = getattr(
        settings, "WORKSPACE_ORPHAN_USE_QUARANTINE_FOR_INVALID_JSON", False
    )
    stale_seconds = getattr(
        settings, "WORKSPACE_ORPHAN_JSON_STALE_MAX_AGE_SECONDS", None
    )

    stats = cleanup_github_activity_tracker_json_cache(
        workspace_dir=workspace_dir,
        execute=True,
        use_quarantine=use_quarantine,
        stale_max_age_seconds=stale_seconds,
        invalid_grace_seconds=None,
    )
    logger.info(
        "Workspace orphan cleanup (github_activity_tracker JSON): scanned=%s "
        "removed_invalid=%s quarantined=%s skipped_grace=%s stale_warnings=%s errors=%s",
        stats.scanned,
        stats.removed_invalid,
        stats.quarantined_invalid,
        stats.skipped_grace_invalid,
        stats.stale_valid_warnings,
        stats.errors,
    )


def should_skip_startup_cleanup() -> bool:
    """Guards: pytest, test settings, and common management commands.

    ``PYTEST_CURRENT_TEST`` is set only while a test runs; during pytest's early
    Django init (e.g. conftest) it is unset, so also treat ``"pytest" in sys.modules``
    as pytest (see config.test_settings).
    """
    if "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    mod = (
        os.environ.get("DJANGO_SETTINGS_MODULE")
        or getattr(settings, "SETTINGS_MODULE", "")
        or ""
    )
    if mod.endswith("test_settings"):
        return True
    argv = sys.argv
    if len(argv) > 1:
        cmd = argv[1]
        if cmd in _SKIP_MANAGEMENT_COMMANDS:
            return True
        # Autoreloader parent must not run workspace IO (child has RUN_MAIN=true).
        if cmd == "runserver" and os.environ.get("RUN_MAIN") != "true":
            return True
    return False


_SKIP_MANAGEMENT_COMMANDS = frozenset(
    {
        "migrate",
        "makemigrations",
        "collectstatic",
        "test",
        "shell",
        "dbshell",
        "flush",
        "dumpdata",
        "loaddata",
        "cleanup_workspace_orphans",
        "migrate_workspace_layout",
        "check",
        "createsuperuser",
    }
)
