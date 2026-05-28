"""Idempotency-under-retry tests for get_or_create_* service functions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from django.db import transaction

from cppa_slack_tracker.models import SlackChannel, SlackTeam
from cppa_slack_tracker.services import (
    get_or_create_slack_channel,
    get_or_create_slack_team,
)
from github_activity_tracker.models import GitHubRepository
from github_activity_tracker.services import get_or_create_repository

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "api_contracts"


def _load_fixture(name: str) -> dict:
    matches = sorted(FIXTURES_DIR.glob(name))
    assert matches, f"no fixture matching {name}"
    return json.loads(matches[0].read_text(encoding="utf-8"))


@pytest.mark.django_db
def test_get_or_create_slack_team_idempotent_under_retry() -> None:
    team_data = _load_fixture("slack_team_*.json")
    with transaction.atomic():
        count_before = SlackTeam.objects.count()
        team1, created1 = get_or_create_slack_team(team_data)
        team2, created2 = get_or_create_slack_team(team_data)
        assert SlackTeam.objects.count() == count_before + 1
        assert team1.pk == team2.pk
        assert created1 is True
        assert created2 is False


@pytest.mark.django_db
def test_get_or_create_slack_channel_idempotent_under_retry(
    sample_slack_team,
    sample_slack_user,
) -> None:
    _ = sample_slack_user
    channel_data = _load_fixture("slack_channel_*.json")
    channel_data = dict(channel_data)
    channel_data["creator"] = sample_slack_user.slack_user_id
    with transaction.atomic():
        count_before = SlackChannel.objects.count()
        ch1, created1 = get_or_create_slack_channel(channel_data, sample_slack_team)
        ch2, created2 = get_or_create_slack_channel(channel_data, sample_slack_team)
        assert ch1 is not None and ch2 is not None
        assert SlackChannel.objects.count() == count_before + 1
        assert ch1.pk == ch2.pk
        assert created1 is True
        assert created2 is False


@pytest.mark.django_db
def test_get_or_create_repository_idempotent_under_retry(github_account) -> None:
    repo_name = "contract-idempotency-repo"
    kwargs = {
        "stars": 10,
        "forks": 2,
        "description": "Idempotency contract test",
    }
    with transaction.atomic():
        count_before = GitHubRepository.objects.count()
        repo1, created1 = get_or_create_repository(github_account, repo_name, **kwargs)
        repo2, created2 = get_or_create_repository(github_account, repo_name, **kwargs)
        assert GitHubRepository.objects.count() == count_before + 1
        assert repo1.pk == repo2.pk
        assert created1 is True
        assert created2 is False
