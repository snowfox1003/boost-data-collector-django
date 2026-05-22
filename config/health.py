"""Readiness checks for /health/ (database, Celery workers, collector freshness)."""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from boost_collector_runner import services as collector_services
from boost_collector_runner.schedule_config import load_config

logger = logging.getLogger(__name__)


def _check_database() -> dict[str, Any]:
    started = time.monotonic()
    try:
        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        latency_ms = int((time.monotonic() - started) * 1000)
        return {"ok": True, "latency_ms": latency_ms}
    except Exception:
        logger.exception("health database check failed")
        return {"ok": False, "error": "database_check_failed"}


def _check_celery_workers() -> dict[str, Any]:
    default_min = 1
    try:
        min_workers = int(getattr(settings, "HEALTH_CELERY_MIN_WORKERS", default_min))
        timeout = float(getattr(settings, "HEALTH_CELERY_INSPECT_TIMEOUT", 3.0))
    except (TypeError, ValueError):
        logger.warning("health celery settings invalid", exc_info=True)
        return {
            "ok": False,
            "workers": [],
            "responded": 0,
            "expected": default_min,
            "error": "celery_settings_invalid",
        }
    try:
        from config.celery import app as celery_app

        inspect = celery_app.control.inspect(timeout=timeout)
        ping = inspect.ping() or {}
        workers = sorted(ping.keys())
        responded = len(workers)
        ok = responded >= min_workers
        return {
            "ok": ok,
            "workers": workers,
            "responded": responded,
            "expected": min_workers,
        }
    except Exception:
        logger.exception("health celery check failed")
        return {
            "ok": False,
            "workers": [],
            "responded": 0,
            "expected": min_workers,
            "error": "celery_check_failed",
        }


def _groups_with_daily_schedule() -> set[str]:
    path = getattr(settings, "BOOST_COLLECTOR_SCHEDULE_YAML", None)
    if path is None:
        from pathlib import Path

        path = Path(settings.BASE_DIR) / "config" / "boost_collector_schedule.yaml"
    data = load_config(path)
    groups = data.get("groups") or {}
    out: set[str] = set()
    for gid, group_data in groups.items():
        if not isinstance(group_data, dict):
            continue
        for task in group_data.get("tasks") or []:
            if not isinstance(task, dict):
                continue
            if task.get("enabled") is False:
                continue
            if task.get("schedule") == "daily":
                out.add(gid)
                break
    return out


def _check_collector_groups() -> dict[str, Any]:
    try:
        stale_hours = float(getattr(settings, "HEALTH_COLLECTOR_STALE_HOURS", 26))
    except (TypeError, ValueError):
        logger.warning("health collector stale-hours setting invalid", exc_info=True)
        return {
            "groups": {},
            "any_stale": False,
            "error": "collector_settings_invalid",
        }
    threshold = timezone.now() - timedelta(hours=stale_hours)
    try:
        statuses = collector_services.list_group_statuses()
    except Exception:
        logger.exception("health collector group check failed")
        return {"groups": {}, "any_stale": False, "error": "collector_check_failed"}
    try:
        daily_groups = _groups_with_daily_schedule()
    except Exception:
        logger.exception("health collector schedule check failed")
        return {
            "groups": {},
            "any_stale": False,
            "error": "collector_schedule_unavailable",
        }
    groups_out: dict[str, Any] = {}
    any_stale = False

    for gid in sorted(daily_groups):
        row = statuses.get(gid)
        last_success = row.last_success_at if row else None
        if last_success is None:
            stale = True
        else:
            stale = last_success < threshold
        if stale:
            any_stale = True
        groups_out[gid] = {
            "last_success_at": last_success.isoformat() if last_success else None,
            "stale": stale,
        }

    for gid, row in sorted(statuses.items()):
        if gid in groups_out:
            continue
        last_success = row.last_success_at
        groups_out[gid] = {
            "last_success_at": last_success.isoformat() if last_success else None,
            "stale": None,
        }

    return {"groups": groups_out, "any_stale": any_stale}


def _check_pinecone_sync() -> dict[str, Any]:
    try:
        from cppa_pinecone_sync.models import PineconeSyncStatus

        rows = PineconeSyncStatus.objects.all().order_by("app_type")
        return {
            app_type: {
                "final_sync_at": (
                    row.final_sync_at.isoformat() if row.final_sync_at else None
                ),
            }
            for row in rows
            for app_type in [row.app_type]
        }
    except Exception:
        logger.exception("health pinecone sync check failed")
        return {"error": "pinecone_sync_check_failed"}


def run_health_checks() -> tuple[dict[str, Any], int]:
    """Run all checks; return (payload, http_status)."""
    db = _check_database()
    celery = _check_celery_workers()
    if db.get("ok"):
        collectors = _check_collector_groups()
        pinecone = _check_pinecone_sync()
    else:
        collectors = {
            "groups": {},
            "any_stale": False,
            "skipped": "database check failed",
        }
        pinecone = {"skipped": "database check failed"}

    enforce_freshness = getattr(settings, "HEALTH_ENFORCE_COLLECTOR_FRESHNESS", True)
    collector_error = bool(collectors.get("error"))
    stale_blocks = enforce_freshness and (
        bool(collectors.get("any_stale")) or collector_error
    )
    critical_ok = db.get("ok") and celery.get("ok") and not stale_blocks
    status_label = "healthy" if critical_ok else "unhealthy"
    http_status = 200 if critical_ok else 503

    collector_meta = {
        "any_stale": bool(collectors.get("any_stale")),
        "enforce_freshness": enforce_freshness,
        "error": collectors.get("error"),
        "skipped": collectors.get("skipped"),
    }

    payload = {
        "status": status_label,
        "checks": {
            "database": db,
            "celery_workers": celery,
            "collector_groups": collectors.get("groups") or {},
            "collector_meta": collector_meta,
            "pinecone_sync": pinecone,
        },
    }
    return payload, http_status


@require_GET
def health_view(request):
    """GET /health/ — readiness for load balancers and Docker HEALTHCHECK."""
    token = (getattr(settings, "HEALTH_CHECK_TOKEN", "") or "").strip()
    if token:
        auth = request.headers.get("Authorization", "")
        expected = f"Bearer {token}"
        if auth != expected:
            return JsonResponse(
                {"status": "unauthorized", "detail": "Invalid or missing token"},
                status=401,
            )

    payload, http_status = run_health_checks()
    return JsonResponse(payload, status=http_status)
