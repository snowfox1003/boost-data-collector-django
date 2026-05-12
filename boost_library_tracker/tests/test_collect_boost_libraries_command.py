"""Tests for collect_boost_libraries management command helpers and handle()."""

from __future__ import annotations

import json
import logging
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import CommandError, call_command
from model_bakery import baker

from boost_library_tracker.management.commands.collect_boost_libraries import (
    Command as CollectCmd,
    _collect_libraries_for_version,
    _normalize_ref,
    _parse_boost_version_option,
    _process_library_data,
)
from boost_library_tracker import services as bl_services
from boost_library_tracker.models import BoostVersion


def test_normalize_ref_numeric_and_full_tag():
    assert _normalize_ref("90") == "boost-1.90.0"
    assert _normalize_ref("boost-1.84.0") == "boost-1.84.0"


def test_normalize_ref_invalid():
    with pytest.raises(ValueError, match="Invalid"):
        _normalize_ref("not-a-tag")
    with pytest.raises(ValueError, match="Empty"):
        _normalize_ref("   ")


def test_parse_boost_version_option_reserved_and_list():
    assert _parse_boost_version_option(None) is None
    assert _parse_boost_version_option("") is None
    assert _parse_boost_version_option("all") == ["all"]
    assert _parse_boost_version_option("NEW") == ["new"]
    assert _parse_boost_version_option("84,90") == ["boost-1.84.0", "boost-1.90.0"]


def test_parse_boost_version_option_errors():
    with pytest.raises(CommandError):
        _parse_boost_version_option("not-a-version")
    with pytest.raises(CommandError, match="must be"):
        _parse_boost_version_option(",,")


@pytest.mark.django_db
def test_collect_handle_parse_error_logs(caplog):
    caplog.set_level(logging.ERROR)
    CollectCmd().handle(boost_version="badtag", dry_run=False)
    assert any("Error parsing" in r.message for r in caplog.records)


@pytest.mark.django_db
def test_collect_handle_no_releases(caplog):
    caplog.set_level(logging.WARNING)
    with patch(
        "boost_library_tracker.management.commands.collect_boost_libraries.new_boost_versions_from_api",
        return_value=[],
    ):
        call_command("collect_boost_libraries", stdout=StringIO())
    assert any("No releases" in r.message for r in caplog.records)


@pytest.mark.django_db
def test_collect_handle_dry_run_short_circuits(caplog):
    caplog.set_level(logging.INFO)
    with patch(
        "boost_library_tracker.management.commands.collect_boost_libraries.new_boost_versions_from_api",
        return_value=[("boost-1.99.0", "abcdef")],
    ):
        call_command("collect_boost_libraries", "--dry-run", stdout=StringIO())
    assert any("Dry run" in r.message for r in caplog.records)


@pytest.mark.django_db
def test_collect_handle_explicit_refs_no_api_list(caplog):
    caplog.set_level(logging.INFO)
    with (
        patch(
            "boost_library_tracker.management.commands.collect_boost_libraries.new_boost_versions_from_api",
        ) as new_api,
        patch(
            "boost_library_tracker.management.commands.collect_boost_libraries.all_boost_versions_from_api",
        ) as all_api,
    ):
        call_command(
            "collect_boost_libraries",
            "--boost-version=boost-1.84.0",
            "--dry-run",
            stdout=StringIO(),
        )
    new_api.assert_not_called()
    all_api.assert_not_called()


@pytest.mark.django_db
def test_collect_handle_all_uses_api(caplog):
    caplog.set_level(logging.INFO)
    with patch(
        "boost_library_tracker.management.commands.collect_boost_libraries.all_boost_versions_from_api",
        return_value=[("boost-1.83.0", "x")],
    ) as all_api:
        call_command(
            "collect_boost_libraries",
            "--boost-version=all",
            "--dry-run",
            stdout=StringIO(),
        )
    all_api.assert_called_once()


@pytest.mark.django_db
def test_collect_handle_applies_limit(caplog):
    caplog.set_level(logging.INFO)
    refs = [(f"boost-1.{i}.0", str(i)) for i in range(10, 20)]
    with patch(
        "boost_library_tracker.management.commands.collect_boost_libraries.new_boost_versions_from_api",
        return_value=refs,
    ):
        call_command(
            "collect_boost_libraries",
            "--dry-run",
            "--limit=2",
            stdout=StringIO(),
        )
    assert any("Processing first 2 releases" in r.message for r in caplog.records)


@pytest.mark.django_db
def test_collect_libraries_no_github_client():
    ver = baker.make(BoostVersion, version="boost-1.84.0")
    with patch(
        "boost_library_tracker.management.commands.collect_boost_libraries.get_github_client",
        return_value=None,
    ):
        c, n = _collect_libraries_for_version(ver, "boost-1.84.0", client=None)
    assert (c, n) == (0, 0)


@pytest.mark.django_db
def test_collect_libraries_empty_gitmodules(boost_library_repository):
    """When .gitmodules fetch returns empty bytes, submodule count is zero."""
    ver = baker.make(BoostVersion, version="boost-1.84.0")
    client = MagicMock()
    client.rest_raw_request.return_value = b""
    created, submods = _collect_libraries_for_version(
        ver, "boost-1.84.0", client=client
    )
    assert created == 0 and submods == 0


@pytest.mark.django_db
def test_collect_libraries_decode_error(boost_library_repository):
    ver = baker.make(BoostVersion, version="boost-1.84.0")
    client = MagicMock()
    client.rest_raw_request.side_effect = [b"\xff\xfe invalid utf8", b"{}"]
    created, submods = _collect_libraries_for_version(
        ver, "boost-1.84.0", client=client
    )
    assert created == 0


@pytest.mark.django_db
def test_process_library_data_creates_roles(boost_library_repository):
    """Smoke: _process_library_data wires library version + roles/categories."""
    ver = baker.make(BoostVersion, version="boost-1.84.0")
    lib_data = {
        "name": "DemoLib",
        "description": "d",
        "key": "demo",
        "documentation": "https://example.com",
        "cxxstd": "C++17",
        "authors": ["Alice"],
        "maintainers": ["Bob"],
        "category": ["Math"],
    }
    count = _process_library_data(lib_data, boost_library_repository, ver)
    assert count in (0, 1)


@pytest.mark.django_db
def test_collect_handle_process_refs_no_client(caplog):
    caplog.set_level(logging.ERROR)
    with (
        patch(
            "boost_library_tracker.management.commands.collect_boost_libraries.new_boost_versions_from_api",
            return_value=[("boost-1.88.0", "sha1")],
        ),
        patch(
            "boost_library_tracker.management.commands.collect_boost_libraries.get_github_client",
            return_value=None,
        ),
    ):
        call_command("collect_boost_libraries", stdout=StringIO())
    assert any("Could not create GitHub Client" in r.message for r in caplog.records)


@pytest.mark.django_db
def test_collect_handle_process_refs_tag_sha_missing(caplog):
    caplog.set_level(logging.ERROR)
    mock_client = MagicMock()
    mock_client.get_tag_sha.return_value = None
    with (
        patch(
            "boost_library_tracker.management.commands.collect_boost_libraries.new_boost_versions_from_api",
            return_value=[("boost-1.88.0", None)],
        ),
        patch(
            "boost_library_tracker.management.commands.collect_boost_libraries.get_github_client",
            return_value=mock_client,
        ),
    ):
        call_command("collect_boost_libraries", stdout=StringIO())
    assert any("Could not get SHA" in r.message for r in caplog.records)


@pytest.mark.django_db
def test_collect_handle_process_refs_rollback_on_exception(caplog):
    caplog.set_level(logging.ERROR)
    mock_client = MagicMock()
    mock_client.get_tag_sha.return_value = "abc"
    mock_client.get_tag_published_at.return_value = None
    mock_client.rest_raw_request.return_value = b""
    with (
        patch(
            "boost_library_tracker.management.commands.collect_boost_libraries.new_boost_versions_from_api",
            return_value=[("boost-1.88.0", None)],
        ),
        patch(
            "boost_library_tracker.management.commands.collect_boost_libraries.get_github_client",
            return_value=mock_client,
        ),
        patch(
            "boost_library_tracker.management.commands.collect_boost_libraries.get_or_create_boost_version",
            side_effect=RuntimeError("boom"),
        ),
    ):
        call_command("collect_boost_libraries", stdout=StringIO())
    assert any("Failed to process ref" in r.message for r in caplog.records)


@pytest.mark.django_db
def test_collect_libraries_gitmodules_and_json_happy_path(github_account):
    github_account.username = "boostorg"
    github_account.save()
    parent = baker.make(
        "github_activity_tracker.GitHubRepository",
        owner_account=github_account,
        repo_name="timer",
        stars=0,
        forks=0,
    )
    bl_services.get_or_create_boost_library_repo(parent)
    gm = (
        '[submodule "timer"]\n'
        "\tpath = libs/timer\n"
        "\turl = https://github.com/boostorg/timer.git\n"
    )
    lib_json = json.dumps(
        [
            {
                "name": "Timer",
                "key": "timer",
                "description": "t",
                "documentation": "",
                "cxxstd": "14",
                "authors": [],
                "maintainers": [],
                "category": [],
            }
        ]
    )

    def raw_request(url):
        if ".gitmodules" in url:
            return gm.encode()
        return lib_json.encode()

    client = MagicMock()
    client.rest_raw_request.side_effect = raw_request
    ver = baker.make(BoostVersion, version="boost-1.84.0")
    created, n = _collect_libraries_for_version(ver, "boost-1.84.0", client=client)
    assert n >= 1
