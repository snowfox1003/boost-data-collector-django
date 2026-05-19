import logging
from typing import ClassVar

from django.apps import AppConfig
from django.conf import settings

logger = logging.getLogger(__name__)


class CoreConfig(AppConfig):
    default_auto_field: ClassVar[str] = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Core"

    def ready(self):
        if not getattr(settings, "WORKSPACE_ORPHAN_CLEANUP_ENABLED", False):
            return
        from core.workspace_orphans import (
            run_startup_workspace_cleanup,
            should_skip_startup_cleanup,
        )

        if should_skip_startup_cleanup():
            return
        try:
            run_startup_workspace_cleanup()
        except Exception:
            logger.exception("Workspace orphan cleanup failed during startup")
