"""
Management command: run_scheduled_collectors
Runs collector commands from config/boost_collector_schedule.yaml for a given schedule.
Use --schedule daily | weekly | monthly | on_release | interval; for weekly pass --day-of-week; for monthly --day-of-month; for interval --interval-minutes (1-180).
Exits with 0 only when all succeed; non-zero on any failure.
With ``--stop-on-failure``, remaining collectors in the run list are not executed; each skipped
collector is logged at WARNING with the failed predecessor and reason.
"""

import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import yaml
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from boost_collector_runner.schedule_config import (
    ScheduleConfigurationError,
    ensure_schedule_yaml_loaded,
    get_tasks_for_schedule,
)
from core import __version__

logger = logging.getLogger(__name__)


def _task_would_run(task, run_on_release_tasks):
    if not run_on_release_tasks and task.get("schedule") == "on_release":
        return False
    return True


def _log_skipped_after_stop_on_failure(
    tasks, failed_index, run_on_release_tasks, reason
):
    for j in range(failed_index + 1, len(tasks)):
        gid, t = tasks[j]
        if not _task_would_run(t, run_on_release_tasks):
            continue
        cmd = t.get("command")
        logger.warning(
            "Skipping collector %r (group=%r): %s",
            cmd,
            gid,
            reason,
        )


class Command(BaseCommand):
    """Run collectors from config/boost_collector_schedule.yaml for a given schedule (daily, weekly, monthly, interval, on_release)."""

    help = (
        "Run collectors from YAML schedule. "
        "Use --schedule daily|weekly|monthly|on_release|interval; weekly needs --day-of-week; monthly needs --day-of-month; interval needs --interval-minutes (1-180)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--schedule",
            choices=(
                "daily",
                "weekly",
                "monthly",
                "on_release",
                "interval",
                "default",
            ),
            required=True,
            help="Schedule type to run. default: daily + weekly(today) + monthly(today) + on_release(if new release).",
        )
        parser.add_argument(
            "--day-of-week",
            type=str,
            default=None,
            help="For weekly: weekday name (e.g. monday, tuesday).",
        )
        parser.add_argument(
            "--day-of-month",
            type=int,
            default=None,
            help="For monthly: day of month 1-31.",
        )
        parser.add_argument(
            "--interval-minutes",
            type=int,
            default=None,
            help="For interval: run every N minutes (1-180, at most 3 hours).",
        )
        parser.add_argument(
            "--group",
            type=str,
            default=None,
            help="Run only this group's tasks. Applies to daily, weekly, monthly, interval, and on_release. Omit to run all groups.",
        )
        parser.add_argument(
            "--stop-on-failure",
            action="store_true",
            help="Stop running remaining collectors after the first failure.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help=(
                "Require schedule YAML to exist and be valid before resolving tasks "
                "(fails even when DEBUG is True)."
            ),
        )

    def handle(self, *args, **options):
        """Resolve tasks from YAML (group batch or single schedule), run them sequentially, exit non-zero on failure."""
        logger.info(
            "run_scheduled_collectors: starting collector_version=%s",
            __version__,
            extra={"collector_version": __version__},
        )
        schedule_kind = options["schedule"]
        day_of_week = options.get("day_of_week")
        day_of_month = options.get("day_of_month")
        interval_minutes = options.get("interval_minutes")
        stop_on_failure = options["stop_on_failure"]
        group_id = options.get("group")
        strict = options["strict"]

        if schedule_kind == "default" and group_id is None:
            raise CommandError("--schedule default requires --group")
        if schedule_kind == "weekly" and not day_of_week:
            raise CommandError("--schedule weekly requires --day-of-week")
        if schedule_kind == "monthly" and day_of_month is None:
            raise CommandError("--schedule monthly requires --day-of-month")
        if schedule_kind == "interval" and interval_minutes is None:
            raise CommandError(
                "--schedule interval requires --interval-minutes (1-180)"
            )

        kwargs = dict(
            schedule_kind=schedule_kind,
            day_of_week=day_of_week,
            day_of_month=day_of_month,
            interval_minutes=interval_minutes,
            group_id=group_id,
        )

        if schedule_kind == "default":
            today = datetime.now(ZoneInfo("UTC")).date()
            kwargs["day_of_week"] = today.strftime("%A").lower()
            kwargs["day_of_month"] = today.day
            kwargs["month"] = today.month
            kwargs["year"] = today.year
        elif schedule_kind == "monthly" and day_of_month is not None:
            tz_name = getattr(settings, "CELERY_TIMEZONE", "UTC")
            today = datetime.now(ZoneInfo(tz_name)).date()
            kwargs["month"] = today.month
            kwargs["year"] = today.year
        if strict:
            try:
                ensure_schedule_yaml_loaded()
            except ScheduleConfigurationError as e:
                raise CommandError(str(e)) from e
        try:
            tasks = get_tasks_for_schedule(**kwargs)
        except (FileNotFoundError, ValueError, yaml.YAMLError) as e:
            raise CommandError(str(e)) from e

        run_on_release_tasks = False

        if schedule_kind == "on_release" or schedule_kind == "default":
            try:
                from boost_library_tracker.release_check import (
                    has_new_boost_release,
                )

                if not has_new_boost_release():
                    logger.info(
                        "run_scheduled_collectors: no new Boost release; skipping on_release tasks."
                    )
                    run_on_release_tasks = False
                else:
                    run_on_release_tasks = True
            except ImportError as e:
                raise CommandError(
                    "on_release requires boost_library_tracker (install and add to INSTALLED_APPS)."
                ) from e
            except Exception as e:
                raise CommandError(f"Failed to check for new Boost release: {e}") from e

        if not tasks:
            logger.info(
                "run_scheduled_collectors: no enabled tasks for schedule=%s",
                schedule_kind,
            )
            self.stdout.write(
                self.style.WARNING(f"No tasks for schedule={schedule_kind}.")
            )
            return

        results = []
        exit_code = 0
        logger.info(
            "run_scheduled_collectors: starting schedule=%s (%d tasks) run_on_release_tasks=%s",
            schedule_kind,
            len(tasks),
            run_on_release_tasks,
        )

        for idx, (_task_group_id, task) in enumerate(tasks):
            if not _task_would_run(task, run_on_release_tasks):
                continue
            name = task.get("command")
            args = task.get("args") or []
            logger.info("Running %s...", name)
            try:
                call_command(name, *args)
                results.append((name, 0))
                logger.info("  %s: success", name)
            except SystemExit as e:
                if e.code is None:
                    code = 0
                elif isinstance(e.code, int):
                    code = e.code
                else:
                    code = 1
                results.append((name, code))
                if code == 0:
                    logger.info("  %s: success", name)
                else:
                    logger.error("%s exited with code %s", name, code)
                    exit_code = code
                    if stop_on_failure:
                        reason = f"stopped after {name!r} exited with code {code}"
                        _log_skipped_after_stop_on_failure(
                            tasks, idx, run_on_release_tasks, reason
                        )
                        break
            except CommandError as e:
                code = getattr(e, "returncode", 1) or 1
                results.append((name, code))
                logger.error("%s failed", name)
                exit_code = code
                if stop_on_failure:
                    reason = f"stopped after {name!r} failed (CommandError)"
                    _log_skipped_after_stop_on_failure(
                        tasks, idx, run_on_release_tasks, reason
                    )
                    break
            except Exception:
                logger.exception("%s failed", name)
                results.append((name, -1))
                exit_code = 1
                if stop_on_failure:
                    reason = f"stopped after {name!r} raised an exception"
                    _log_skipped_after_stop_on_failure(
                        tasks, idx, run_on_release_tasks, reason
                    )
                    break

        succeeded = sum(1 for _, code in results if code == 0)
        failed = len(results) - succeeded
        logger.info(
            "run_scheduled_collectors: finished; succeeded=%d, failed=%d",
            succeeded,
            failed,
        )
        summary = f"Summary: {succeeded} succeeded, {failed} failed."
        if failed == 0:
            logger.info(summary)
        else:
            logger.warning(summary)

        if exit_code != 0:
            sys.exit(exit_code)
