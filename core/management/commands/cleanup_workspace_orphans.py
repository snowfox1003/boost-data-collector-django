"""
Scan WORKSPACE_DIR for orphan artifacts:
  - Temp suffixes: *.tmp, *.part, *.lock, *.swp (age-based)
  - Optional: github_activity_tracker JSON cache files that are empty or invalid JSON
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, cast

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.workspace_orphans import cleanup_github_activity_tracker_json_cache

logger = logging.getLogger(__name__)

_ORPHAN_SUFFIXES = (".tmp", ".part", ".lock", ".swp")


class Command(BaseCommand):
    help = (
        "List or remove stale workspace files: (1) suffixes matching partial-write patterns "
        f"{_ORPHAN_SUFFIXES}, optionally (2) invalid/empty JSON under "
        "github_activity_tracker/.../{commits,issues,prs}/"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-age-hours",
            type=float,
            default=24.0,
            help="For suffix scan only: only files not modified within this many hours (default: 24).",
        )
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Delete matching files; default is dry-run for suffixes. "
            "When combined with --github-json-cache, applies deletions/quarantine there too.",
        )
        parser.add_argument(
            "--github-json-cache",
            action="store_true",
            help=(
                "Also scan github_activity_tracker JSON cache; remove/quarantine empty or invalid JSON."
            ),
        )

    def handle(self, *args, **options):
        max_age = float(options["max_age_hours"])
        if max_age < 0:
            raise CommandError(
                f"--max-age-hours must be zero or positive (got {max_age})."
            )
        execute = options["execute"]
        root = Path(getattr(settings, "WORKSPACE_DIR", ""))
        style = cast(Any, self.style)
        if not root.is_dir():
            self.stderr.write(style.ERROR(f"WORKSPACE_DIR is not a directory: {root}"))
            return

        suffix_found = self._run_suffix_scan(root, max_age, execute, style)

        gh_stats = None
        if options["github_json_cache"]:
            gh_stats = cleanup_github_activity_tracker_json_cache(
                workspace_dir=root,
                execute=execute,
                use_quarantine=getattr(
                    settings, "WORKSPACE_ORPHAN_USE_QUARANTINE_FOR_INVALID_JSON", False
                ),
                stale_max_age_seconds=getattr(
                    settings, "WORKSPACE_ORPHAN_JSON_STALE_MAX_AGE_SECONDS", None
                ),
                invalid_grace_seconds=None,
            )
            rel = "Removed" if execute else "Would remove / logged"
            self.stdout.write(
                style.NOTICE(
                    f"{rel} github_activity_tracker invalid JSON: scanned={gh_stats.scanned} "
                    f"removed_invalid={gh_stats.removed_invalid} "
                    f"quarantined={gh_stats.quarantined_invalid} "
                    f"skipped_grace={gh_stats.skipped_grace_invalid} "
                    f"stale_warnings={gh_stats.stale_valid_warnings} errors={gh_stats.errors}"
                )
            )

        self.stdout.write(
            style.NOTICE(
                f"{'Removed' if execute else 'Found'} {suffix_found} orphan suffix candidate(s) "
                f"(suffix in {_ORPHAN_SUFFIXES}, older than {max_age}h)."
            )
        )

    def _run_suffix_scan(
        self, root: Path, max_age: float, execute: bool, style: Any
    ) -> int:
        cutoff = time.time() - max_age * 3600.0
        found: list[Path] = []
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if not path.name.endswith(_ORPHAN_SUFFIXES):
                continue
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if mtime > cutoff:
                continue
            found.append(path)

        for p in sorted(found):
            rel = p.relative_to(root)
            if execute:
                try:
                    p.unlink()
                    self.stdout.write(style.SUCCESS(f"deleted {rel}"))
                except OSError as e:
                    logger.warning("Could not delete %s: %s", p, e)
                    self.stderr.write(style.WARNING(f"skip {rel}: {e}"))
            else:
                self.stdout.write(f"would delete (dry-run): {rel}")

        return len(found)
