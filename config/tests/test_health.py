"""Tests for config.health readiness checks."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import Client, override_settings
from django.utils import timezone

from boost_collector_runner import services as collector_services
from config.health import (
    _check_celery_workers,
    _check_collector_groups,
    _check_database,
    _check_pinecone_sync,
    _groups_with_daily_schedule,
    run_health_checks,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client():
    return Client()


@override_settings(HEALTH_COLLECTOR_STALE_HOURS=26)
def test_health_view_healthy_when_db_and_celery_ok(api_client):
    now = timezone.now()
    for gid in _groups_with_daily_schedule():
        collector_services.record_group_success(gid, when=now)
    with patch("config.health._check_celery_workers") as mock_celery:
        mock_celery.return_value = {
            "ok": True,
            "workers": ["celery@host"],
            "responded": 1,
            "expected": 1,
        }
        response = api_client.get("/health/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["checks"]["database"]["ok"] is True


@override_settings(
    HEALTH_COLLECTOR_STALE_HOURS=26,
    HEALTH_ENFORCE_COLLECTOR_FRESHNESS=True,
)
def test_health_view_503_when_stale_group(api_client):
    old = timezone.now() - timedelta(hours=48)
    collector_services.record_group_success("github", when=old)
    with patch("config.health._check_celery_workers") as mock_celery:
        mock_celery.return_value = {
            "ok": True,
            "workers": ["celery@host"],
            "responded": 1,
            "expected": 1,
        }
        with patch(
            "config.health._groups_with_daily_schedule", return_value={"github"}
        ):
            response = api_client.get("/health/")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["checks"]["collector_meta"]["any_stale"] is True
    assert data["checks"]["collector_meta"]["enforce_freshness"] is True
    assert data["checks"]["collector_meta"]["error"] is None


@override_settings(HEALTH_CHECK_TOKEN="secret-token")
def test_health_view_requires_bearer_when_token_set(api_client):
    response = api_client.get("/health/")
    assert response.status_code == 401
    response = api_client.get("/health/", HTTP_AUTHORIZATION="Bearer secret-token")
    assert response.status_code in (200, 503)


def test_run_health_checks_celery_failure():
    with patch("config.health._check_celery_workers") as mock_celery:
        mock_celery.return_value = {
            "ok": False,
            "workers": [],
            "responded": 0,
            "expected": 1,
        }
        payload, status = run_health_checks()
    assert status == 503
    assert payload["checks"]["celery_workers"]["ok"] is False


def test_run_health_checks_db_failure_returns_json_not_500():
    with patch("config.health._check_database") as mock_db:
        mock_db.return_value = {"ok": False, "error": "database_check_failed"}
        with patch("config.health._check_celery_workers") as mock_celery:
            mock_celery.return_value = {
                "ok": True,
                "workers": ["celery@host"],
                "responded": 1,
                "expected": 1,
            }
            payload, status = run_health_checks()
    assert status == 503
    assert payload["status"] == "unhealthy"
    assert payload["checks"]["database"]["ok"] is False
    assert payload["checks"]["collector_groups"] == {}
    assert payload["checks"]["collector_meta"]["skipped"] == "database check failed"


def test_check_database_exception_returns_stable_error():
    sensitive = "postgres://secret:password@10.0.0.5:5432/internal"
    with patch(
        "config.health.connection.ensure_connection",
        side_effect=RuntimeError(sensitive),
    ):
        result = _check_database()
    assert result == {"ok": False, "error": "database_check_failed"}


def test_check_celery_workers_exception_returns_stable_error():
    sensitive = "redis://:token@internal.cache:6379/0"
    with patch(
        "config.celery.app.control.inspect",
        side_effect=RuntimeError(sensitive),
    ):
        result = _check_celery_workers()
    assert result["ok"] is False
    assert result["error"] == "celery_check_failed"
    assert sensitive not in str(result)


@override_settings(HEALTH_CELERY_MIN_WORKERS="not-a-number")
def test_check_celery_workers_invalid_min_workers_returns_stable_error():
    result = _check_celery_workers()
    assert result == {
        "ok": False,
        "workers": [],
        "responded": 0,
        "expected": 1,
        "error": "celery_settings_invalid",
    }


@override_settings(HEALTH_CELERY_INSPECT_TIMEOUT="bad")
def test_check_celery_workers_invalid_timeout_returns_stable_error():
    result = _check_celery_workers()
    assert result["ok"] is False
    assert result["error"] == "celery_settings_invalid"


@override_settings(HEALTH_COLLECTOR_STALE_HOURS="twenty-six")
def test_check_collector_groups_invalid_stale_hours_returns_stable_error():
    result = _check_collector_groups()
    assert result == {
        "groups": {},
        "any_stale": False,
        "error": "collector_settings_invalid",
    }


@override_settings(
    HEALTH_CELERY_MIN_WORKERS="nope",
    HEALTH_ENFORCE_COLLECTOR_FRESHNESS=True,
)
def test_health_view_invalid_celery_setting_returns_503_not_500(api_client):
    response = api_client.get("/health/")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["checks"]["celery_workers"]["error"] == "celery_settings_invalid"


def test_check_collector_groups_exception_returns_stable_error():
    sensitive = "SELECT * FROM secret_table"
    with patch(
        "config.health.collector_services.list_group_statuses",
        side_effect=RuntimeError(sensitive),
    ):
        result = _check_collector_groups()
    assert result == {
        "groups": {},
        "any_stale": False,
        "error": "collector_check_failed",
    }


def test_check_collector_groups_schedule_failure_returns_stable_error():
    with patch(
        "config.health.load_config",
        side_effect=ValueError("invalid yaml at line 99"),
    ):
        result = _check_collector_groups()
    assert result == {
        "groups": {},
        "any_stale": False,
        "error": "collector_schedule_unavailable",
    }
    assert "line 99" not in str(result)


@override_settings(HEALTH_ENFORCE_COLLECTOR_FRESHNESS=True)
def test_run_health_checks_503_when_collector_schedule_unavailable():
    with patch("config.health._check_celery_workers") as mock_celery:
        mock_celery.return_value = {
            "ok": True,
            "workers": ["celery@host"],
            "responded": 1,
            "expected": 1,
        }
        with patch(
            "config.health.load_config", side_effect=FileNotFoundError("missing")
        ):
            payload, status = run_health_checks()
    assert status == 503
    assert payload["status"] == "unhealthy"
    assert (
        payload["checks"]["collector_meta"]["error"] == "collector_schedule_unavailable"
    )
    assert payload["checks"]["collector_meta"]["enforce_freshness"] is True


@override_settings(HEALTH_ENFORCE_COLLECTOR_FRESHNESS=False)
def test_run_health_checks_healthy_when_collector_check_errors_but_freshness_disabled():
    with patch("config.health._check_celery_workers") as mock_celery:
        mock_celery.return_value = {
            "ok": True,
            "workers": ["celery@host"],
            "responded": 1,
            "expected": 1,
        }
        with patch(
            "config.health.collector_services.list_group_statuses",
            side_effect=RuntimeError("db down"),
        ):
            payload, status = run_health_checks()
    assert status == 200
    assert payload["status"] == "healthy"
    assert payload["checks"]["collector_meta"]["enforce_freshness"] is False
    assert payload["checks"]["collector_meta"]["error"] == "collector_check_failed"


def test_check_pinecone_sync_exception_returns_stable_error():
    sensitive = "pc-secret-api-key-abcdef"
    with patch(
        "cppa_pinecone_sync.models.PineconeSyncStatus.objects.all",
        side_effect=RuntimeError(sensitive),
    ):
        result = _check_pinecone_sync()
    assert result == {"error": "pinecone_sync_check_failed"}
