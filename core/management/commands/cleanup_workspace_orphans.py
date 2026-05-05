"""
Scan WORKSPACE_DIR for common orphan temp artifacts (e.g. *.tmp, *.part, *.lock).
Log or delete based on age. Does not delete arbitrary unknown files without suffix match.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)

_ORPHAN_SUFFIXES = (".tmp", ".part", ".lock", ".swp")


class Command(BaseCommand):
    help = (
        "List or remove stale workspace files matching common partial-write suffixes "
        f"{_ORPHAN_SUFFIXES} under WORKSPACE_DIR."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-age-hours",
            type=float,
            default=24.0,
            help="Only consider files not modified within this many hours (default: 24).",
        )
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Delete matching files; default is dry-run (log only).",
        )

    def handle(self, *args, **options):
        max_age = float(options["max_age_hours"])
        if max_age < 0:
            raise CommandError(
                f"--max-age-hours must be zero or positive (got {max_age})."
            )
        execute = options["execute"]
        root = Path(getattr(settings, "WORKSPACE_DIR", ""))
        if not root.is_dir():
            self.stderr.write(
                self.style.ERROR(f"WORKSPACE_DIR is not a directory: {root}")
            )
            return

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
                    self.stdout.write(self.style.SUCCESS(f"deleted {rel}"))
                except OSError as e:
                    logger.warning("Could not delete %s: %s", p, e)
                    self.stderr.write(self.style.WARNING(f"skip {rel}: {e}"))
            else:
                self.stdout.write(f"would delete (dry-run): {rel}")

        self.stdout.write(
            self.style.NOTICE(
                f"{'Removed' if execute else 'Found'} {len(found)} orphan candidate(s) "
                f"(suffix in {_ORPHAN_SUFFIXES}, older than {max_age}h)."
            )
        )
