"""
Management command: run_cppa_user_tracker
Syncs identity and profile data; stages profile-to-identity relations (TmpIdentity,
TempProfileIdentityRelation) before merging. Implements restart logic per Development_guideline.
"""

from __future__ import annotations

import logging
from typing import Any

from core.collectors.base import CollectorBase
from core.collectors.command_base import BaseCollectorCommand

logger = logging.getLogger(__name__)


class CppaUserTrackerCollector(CollectorBase):
    """Identity/profile staging (stub until merge logic is implemented)."""

    def __init__(self, *, stdout: Any, style: Any) -> None:
        self.stdout = stdout
        self.style = style

    def run(self) -> None:
        logger.info("run_cppa_user_tracker: starting")
        # Stub: add logic (stage relations, merge into Identity/BaseProfile, etc.)
        self.stdout.write(self.style.SUCCESS("CPPA User Tracker completed (stub)."))
        logger.info("run_cppa_user_tracker: finished successfully")


class Command(BaseCollectorCommand):
    help = "Run the CPPA User Tracker (identity/profile staging and merge)."

    def get_collector(self, **_options: Any) -> CollectorBase:
        return CppaUserTrackerCollector(stdout=self.stdout, style=self.style)
