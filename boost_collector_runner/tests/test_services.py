"""Tests for boost_collector_runner.services."""

import pytest
from django.utils import timezone

from boost_collector_runner import services
from boost_collector_runner.models import CollectorGroupRunStatus

pytestmark = pytest.mark.django_db


def test_record_group_success_creates_row():
    when = timezone.now()
    row = services.record_group_success("github", when=when)
    assert row.group_id == "github"
    assert row.last_success_at == when
    assert row.last_exit_code == 0
    assert CollectorGroupRunStatus.objects.filter(group_id="github").exists()


def test_record_group_failure_sets_exit_code():
    when = timezone.now()
    row = services.record_group_failure("slack", exit_code=2, when=when)
    assert row.last_failure_at == when
    assert row.last_exit_code == 2


def test_list_group_statuses():
    services.record_group_success("github")
    statuses = services.list_group_statuses()
    assert "github" in statuses
