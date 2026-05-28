"""Contract tests: recorded API fixtures must parse through boundary schemas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from cppa_slack_tracker.api_schemas import (
    SlackApiValidationError,
    parse_channel,
    parse_message,
    parse_team,
    parse_user,
)
from github_activity_tracker.api_schemas import (
    GitHubApiValidationError,
    parse_commit,
    parse_issue_bundle,
    parse_pr_bundle,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "api_contracts"


def _load_fixture(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _fixture_paths(prefix: str) -> list[Path]:
    paths = sorted(FIXTURES_DIR.glob(f"{prefix}_*.json"))
    if not paths:
        raise ValueError(f"no fixtures found for prefix '{prefix}'")
    return paths


# --- GitHub ---


@pytest.mark.parametrize(
    "fixture_path",
    _fixture_paths("github_issue_bundle"),
    ids=[p.name for p in _fixture_paths("github_issue_bundle")],
)
def test_github_issue_bundle_contract(fixture_path: Path) -> None:
    bundle = parse_issue_bundle(_load_fixture(fixture_path), source=fixture_path.name)
    assert bundle.issue.number >= 1


@pytest.mark.parametrize(
    "fixture_path",
    _fixture_paths("github_pr_bundle"),
    ids=[p.name for p in _fixture_paths("github_pr_bundle")],
)
def test_github_pr_bundle_contract(fixture_path: Path) -> None:
    bundle = parse_pr_bundle(_load_fixture(fixture_path), source=fixture_path.name)
    assert bundle.pr.number >= 1


@pytest.mark.parametrize(
    "fixture_path",
    _fixture_paths("github_commit"),
    ids=[p.name for p in _fixture_paths("github_commit")],
)
def test_github_commit_contract(fixture_path: Path) -> None:
    commit = parse_commit(_load_fixture(fixture_path), source=fixture_path.name)
    assert len(commit.sha) >= 1


# --- Slack ---


@pytest.mark.parametrize(
    "fixture_path",
    _fixture_paths("slack_team"),
    ids=[p.name for p in _fixture_paths("slack_team")],
)
def test_slack_team_contract(fixture_path: Path) -> None:
    team = parse_team(_load_fixture(fixture_path), source=fixture_path.name)
    assert team.team_id


@pytest.mark.parametrize(
    "fixture_path",
    _fixture_paths("slack_channel"),
    ids=[p.name for p in _fixture_paths("slack_channel")],
)
def test_slack_channel_contract(fixture_path: Path) -> None:
    channel = parse_channel(_load_fixture(fixture_path), source=fixture_path.name)
    assert channel.id


@pytest.mark.parametrize(
    "fixture_path",
    _fixture_paths("slack_user"),
    ids=[p.name for p in _fixture_paths("slack_user")],
)
def test_slack_user_contract(fixture_path: Path) -> None:
    user = parse_user(_load_fixture(fixture_path), source=fixture_path.name)
    assert user.id


@pytest.mark.parametrize(
    "fixture_path",
    _fixture_paths("slack_message"),
    ids=[p.name for p in _fixture_paths("slack_message")],
)
def test_slack_message_contract(fixture_path: Path) -> None:
    message = parse_message(_load_fixture(fixture_path), source=fixture_path.name)
    assert message.ts is not None


# --- Negative sanity: contract tests detect broken required fields ---


def test_github_issue_bundle_contract_fails_without_number() -> None:
    data = _load_fixture(_fixture_paths("github_issue_bundle")[0])
    if "issue_info" in data:
        del data["issue_info"]["number"]
    else:
        del data["issue"]["number"]
    with pytest.raises(GitHubApiValidationError):
        parse_issue_bundle(data)


def test_slack_team_contract_fails_without_id() -> None:
    data = _load_fixture(_fixture_paths("slack_team")[0])
    data.pop("id", None)
    data.pop("team_id", None)
    with pytest.raises(SlackApiValidationError):
        parse_team(data)
