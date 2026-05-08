"""Tests for core.workspace_orphans."""

import json
import os
import sys
import time
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.management import call_command


def _gat_commit_json(workspace: Path, owner="boostorg", repo="wave"):
    d = workspace / "github_activity_tracker" / owner / repo / "commits"
    d.mkdir(parents=True)
    return d


@pytest.mark.django_db
def test_classify_json_file(tmp_path):
    from core.workspace_orphans import classify_json_file

    empty = tmp_path / "e.json"
    empty.write_text("", encoding="utf-8")
    assert classify_json_file(empty) == "empty"

    bad = tmp_path / "b.json"
    bad.write_text("{", encoding="utf-8")
    assert classify_json_file(bad) == "invalid"

    ok = tmp_path / "o.json"
    ok.write_text(json.dumps({"a": 1}), encoding="utf-8")
    assert classify_json_file(ok) == "valid"


@pytest.mark.django_db
def test_classify_json_file_non_utf8_invalid(tmp_path):
    from core.workspace_orphans import classify_json_file

    p = tmp_path / "bad.json"
    p.write_bytes(b"\xff\xfe{\x00")

    assert classify_json_file(p) == "invalid"


@pytest.mark.django_db
def test_cleanup_removes_invalid_json_execute(tmp_path):
    from core.workspace_orphans import cleanup_github_activity_tracker_json_cache

    p = _gat_commit_json(tmp_path) / "abc.json"
    p.write_text("{not json", encoding="utf-8")

    stats = cleanup_github_activity_tracker_json_cache(
        workspace_dir=tmp_path,
        execute=True,
        use_quarantine=False,
        stale_max_age_seconds=None,
        invalid_grace_seconds=0.0,
    )
    assert stats.scanned == 1
    assert stats.removed_invalid == 1
    assert not p.exists()


@pytest.mark.django_db
def test_cleanup_removes_non_utf8_cache_file(tmp_path):
    from core.workspace_orphans import cleanup_github_activity_tracker_json_cache

    p = _gat_commit_json(tmp_path) / "bin.json"
    p.write_bytes(b"\xff\xfe\x00\x00{")

    stats = cleanup_github_activity_tracker_json_cache(
        workspace_dir=tmp_path,
        execute=True,
        use_quarantine=False,
        stale_max_age_seconds=None,
        invalid_grace_seconds=0.0,
    )
    assert stats.scanned == 1
    assert stats.removed_invalid == 1
    assert not p.exists()


@pytest.mark.django_db
def test_cleanup_dry_run_keeps_invalid(tmp_path):
    from core.workspace_orphans import cleanup_github_activity_tracker_json_cache

    p = _gat_commit_json(tmp_path) / "abc.json"
    p.write_text("{", encoding="utf-8")

    stats = cleanup_github_activity_tracker_json_cache(
        workspace_dir=tmp_path,
        execute=False,
        use_quarantine=False,
        stale_max_age_seconds=None,
        invalid_grace_seconds=0.0,
    )
    assert stats.removed_invalid == 1
    assert p.exists()


@pytest.mark.django_db
def test_should_skip_when_pytest_current_test():
    from core import workspace_orphans as wo

    with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": "core/tests/x.py::test_y"}):
        assert wo.should_skip_startup_cleanup() is True


@pytest.mark.django_db
def test_should_skip_when_runserver_parent():
    from core import workspace_orphans as wo

    saved_rm = os.environ.pop("RUN_MAIN", None)
    saved_pt = os.environ.pop("PYTEST_CURRENT_TEST", None)
    saved_pytest = sys.modules.pop("pytest", None)
    try:
        with patch.dict(os.environ, {"DJANGO_SETTINGS_MODULE": "config.settings"}):
            with patch.object(sys, "argv", ["manage.py", "runserver"]):
                assert wo.should_skip_startup_cleanup() is True
            os.environ["RUN_MAIN"] = "true"
            with patch.object(sys, "argv", ["manage.py", "runserver"]):
                assert wo.should_skip_startup_cleanup() is False
    finally:
        os.environ.pop("RUN_MAIN", None)
        if saved_rm is not None:
            os.environ["RUN_MAIN"] = saved_rm
        if saved_pt is not None:
            os.environ["PYTEST_CURRENT_TEST"] = saved_pt
        if saved_pytest is not None:
            sys.modules["pytest"] = saved_pytest


@pytest.mark.django_db
def test_should_skip_migrate_argv():
    from core import workspace_orphans as wo

    saved = os.environ.pop("PYTEST_CURRENT_TEST", None)
    try:
        with patch.object(sys, "argv", ["manage.py", "migrate"]):
            assert wo.should_skip_startup_cleanup() is True
    finally:
        if saved is not None:
            os.environ["PYTEST_CURRENT_TEST"] = saved


@pytest.mark.django_db
def test_cleanup_skips_invalid_json_within_grace_period(tmp_path):
    from core.workspace_orphans import cleanup_github_activity_tracker_json_cache

    p = _gat_commit_json(tmp_path) / "mid.json"
    p.write_text("{", encoding="utf-8")

    stats = cleanup_github_activity_tracker_json_cache(
        workspace_dir=tmp_path,
        execute=True,
        use_quarantine=False,
        stale_max_age_seconds=None,
        invalid_grace_seconds=3600.0,
    )
    assert p.exists()
    assert stats.skipped_grace_invalid == 1
    assert stats.removed_invalid == 0


@pytest.mark.django_db
def test_cleanup_removes_invalid_after_grace(tmp_path):
    from core.workspace_orphans import cleanup_github_activity_tracker_json_cache

    p = _gat_commit_json(tmp_path) / "old.json"
    p.write_text("{", encoding="utf-8")
    old = time.time() - 60.0
    os.utime(p, (old, old))

    stats = cleanup_github_activity_tracker_json_cache(
        workspace_dir=tmp_path,
        execute=True,
        use_quarantine=False,
        stale_max_age_seconds=None,
        invalid_grace_seconds=5.0,
    )
    assert not p.exists()
    assert stats.removed_invalid == 1
    assert stats.skipped_grace_invalid == 0


@pytest.mark.django_db
def test_concurrent_unlink_file_not_found_not_error(tmp_path):
    """Another worker may delete the same orphan first (multi-worker WSGI)."""
    from pathlib import Path
    from unittest.mock import patch

    from core.workspace_orphans import cleanup_github_activity_tracker_json_cache

    p = _gat_commit_json(tmp_path) / "race.json"
    p.write_text("{", encoding="utf-8")

    real_unlink = Path.unlink

    def unlink_simulate_other_worker(self, missing_ok=False):
        try:
            self.relative_to(tmp_path)
        except ValueError:
            return real_unlink(self, missing_ok=missing_ok)
        raise FileNotFoundError()

    with patch.object(Path, "unlink", unlink_simulate_other_worker):
        stats = cleanup_github_activity_tracker_json_cache(
            workspace_dir=tmp_path,
            execute=True,
            use_quarantine=False,
            stale_max_age_seconds=None,
            invalid_grace_seconds=0.0,
        )

    assert stats.errors == 0
    assert stats.removed_invalid == 0


@pytest.mark.django_db
def test_management_command_github_json_cache_removes_invalid(tmp_path):
    bad = _gat_commit_json(tmp_path) / "x.json"
    bad.write_text("", encoding="utf-8")

    with patch("django.conf.settings.WORKSPACE_DIR", tmp_path):
        with patch(
            "django.conf.settings.WORKSPACE_ORPHAN_INVALID_JSON_GRACE_SECONDS", 0.0
        ):
            out = StringIO()
            call_command(
                "cleanup_workspace_orphans",
                "--github-json-cache",
                "--execute",
                stdout=out,
            )
    assert not bad.exists()
    body = out.getvalue().replace(" ", "")
    assert "removed_invalid=1" in body


@pytest.mark.django_db
def test_stale_valid_json_logs_warning_only(tmp_path, caplog):
    import logging

    from core.workspace_orphans import cleanup_github_activity_tracker_json_cache

    p = _gat_commit_json(tmp_path) / "good.json"
    p.write_text(json.dumps({"ok": True}), encoding="utf-8")
    old = time.time() - 10 * 24 * 3600
    os.utime(p, (old, old))

    with caplog.at_level(logging.WARNING):
        cleanup_github_activity_tracker_json_cache(
            workspace_dir=tmp_path,
            execute=True,
            use_quarantine=False,
            stale_max_age_seconds=3600.0,
            invalid_grace_seconds=0.0,
        )
    assert p.exists()
    assert any("Stale valid JSON" in r.message for r in caplog.records)
