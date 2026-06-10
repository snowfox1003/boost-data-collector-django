"""Tests for run_boost_library_docs_tracker management command."""

from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone as dj_tz

from boost_library_docs_tracker.management.commands.run_boost_library_docs_tracker import (
    BoostLibraryDocsTrackerCollector,
    Command,
    _sort_versions_by_db,
)
from boost_library_tracker import services as bl_services


@pytest.mark.django_db
def test_sort_versions_by_db_orders_by_created_at():
    """Versions sort oldest→newest using BoostVersion.version_created_at."""
    older, _ = bl_services.get_or_create_boost_version(
        "boost-1.80.0",
        version_created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    newer, _ = bl_services.get_or_create_boost_version(
        "boost-1.81.0",
        version_created_at=datetime(2021, 1, 1, tzinfo=timezone.utc),
    )
    assert older.pk and newer.pk
    out = _sort_versions_by_db(["boost-1.81.0", "boost-1.80.0"])
    assert out == ["boost-1.80.0", "boost-1.81.0"]


@pytest.mark.django_db
def test_sort_versions_by_db_unknown_last():
    """Tags missing from DB keep relative order at the end."""
    bl_services.get_or_create_boost_version(
        "boost-1.82.0",
        version_created_at=dj_tz.now(),
    )
    out = _sort_versions_by_db(["boost-9.99.0", "boost-1.82.0", "boost-9.98.0"])
    assert out[0] == "boost-1.82.0"
    assert set(out[1:]) == {"boost-9.99.0", "boost-9.98.0"}


@pytest.mark.django_db
def test_resolve_versions_explicit_prefix_and_strip(boost_library_version):
    """Explicit --versions normalizes to boost-* and sorts."""
    ver = boost_library_version.version
    ver.version = "boost-1.81.0"
    ver.version_created_at = dj_tz.now()
    ver.save()
    cmd = Command()
    resolved = cmd._resolve_versions(["  1.81.0 ", "boost-1.80.0"])
    assert "boost-1.81.0" in resolved


@pytest.mark.django_db
def test_resolve_versions_latest_from_db(boost_library_version):
    """When versions omitted, use latest BoostVersion with version_created_at set."""
    ver = boost_library_version.version
    ver.version = "boost-1.81.0"
    ver.version_created_at = dj_tz.now()
    ver.save()
    cmd = Command()
    resolved = cmd._resolve_versions(None)
    assert resolved == ["boost-1.81.0"]


@pytest.mark.django_db
def test_resolve_versions_no_rows_raises():
    cmd = Command()
    with pytest.raises(CommandError, match="No BoostVersion"):
        cmd._resolve_versions(None)


@pytest.mark.django_db
def test_get_library_list_unknown_version_raises():
    cmd = Command()
    with pytest.raises(CommandError, match="not found in DB"):
        cmd._get_library_list("boost-9.99.0")


@pytest.mark.django_db
def test_get_library_list_uses_key_or_doc(boost_library_version):
    cmd = Command()
    lv = boost_library_version
    lv.key = "algokey"
    lv.documentation = "https://example.com/doc/"
    lv.save()
    ver = lv.version
    ver.version = "boost-1.81.0"
    ver.save()
    with patch(
        "boost_library_docs_tracker.management.commands.run_boost_library_docs_tracker.fetcher.get_start_path",
        return_value=Path("/tmp/start"),
    ) as gsp:
        pairs = cmd._get_library_list("boost-1.81.0")
    assert len(pairs) == 1
    gsp.assert_called_once_with("algokey", "https://example.com/doc/")


@pytest.mark.django_db
def test_resolve_library_version_id_by_key_then_name(boost_library, boost_version):
    lv_key, _ = bl_services.get_or_create_boost_library_version(
        boost_library,
        boost_version,
        key="mykey",
        documentation="",
    )
    boost_version.version = "boost-1.81.0"
    boost_version.save()
    cmd = Command()
    assert cmd._resolve_library_version_id("mykey", "boost-1.81.0") == lv_key.pk
    assert (
        cmd._resolve_library_version_id(boost_library.name, "boost-1.81.0") == lv_key.pk
    )


@pytest.mark.django_db
def test_resolve_boost_version_id(boost_version):
    boost_version.version = "boost-1.81.0"
    boost_version.save()
    cmd = Command()
    assert cmd._resolve_boost_version_id("boost-1.81.0") == boost_version.pk
    assert cmd._resolve_boost_version_id("boost-missing") is None


@pytest.mark.django_db
def test_process_version_library_filter_missing_raises(boost_library_version):
    ver = boost_library_version.version
    ver.version = "boost-1.81.0"
    ver.save()
    cmd = Command()
    with pytest.raises(CommandError, match="not found"):
        cmd._process_version(
            version="boost-1.81.0",
            library_filter="nonexistent_lib",
            dry_run=True,
            max_pages=5,
            use_local=False,
            cleanup_extract=False,
        )


@pytest.mark.django_db
def test_prepare_local_source_download_error():
    cmd = Command()
    with patch(
        "boost_library_docs_tracker.management.commands.run_boost_library_docs_tracker.fetcher.download_source_zip",
        side_effect=RuntimeError("net"),
    ):
        with pytest.raises(CommandError, match="Failed to download"):
            cmd._prepare_local_source(version="boost-1.81.0")


@pytest.mark.django_db
def test_prepare_local_source_extract_error():
    cmd = Command()
    zip_path = Path("/fake/z.zip")
    with (
        patch(
            "boost_library_docs_tracker.management.commands.run_boost_library_docs_tracker.fetcher.download_source_zip",
            return_value=zip_path,
        ),
        patch(
            "boost_library_docs_tracker.management.commands.run_boost_library_docs_tracker.fetcher.extract_source_zip",
            side_effect=ValueError("bad zip"),
        ),
    ):
        with pytest.raises(CommandError, match="Failed to extract"):
            cmd._prepare_local_source(version="boost-1.81.0")


@pytest.mark.django_db
def test_process_library_crawl_error_returns_zero(boost_library_version):
    lv = boost_library_version
    ver = lv.version
    ver.version = "boost-1.81.0"
    ver.save()
    cmd = Command()
    with patch(
        "boost_library_docs_tracker.management.commands.run_boost_library_docs_tracker.fetcher.crawl_library_pages",
        side_effect=RuntimeError("boom"),
    ):
        n = cmd._process_library(
            version="boost-1.81.0",
            lib_key="algorithm",
            start_path=Path("."),
            use_local=False,
            dry_run=False,
            max_pages=10,
            boost_version_id=ver.pk,
        )
    assert n == 0


@pytest.mark.django_db
def test_process_library_local_walk_error_returns_zero(boost_library_version):
    lv = boost_library_version
    ver = lv.version
    ver.version = "boost-1.81.0"
    ver.save()
    cmd = Command()
    with patch(
        "boost_library_docs_tracker.management.commands.run_boost_library_docs_tracker.fetcher.walk_library_html",
        side_effect=RuntimeError("walk"),
    ):
        n = cmd._process_library(
            version="boost-1.81.0",
            lib_key="algorithm",
            start_path=Path("."),
            use_local=True,
            dry_run=False,
            max_pages=10,
            boost_version_id=ver.pk,
        )
    assert n == 0


@pytest.mark.django_db
def test_process_library_skips_db_when_no_library_version(boost_library_version):
    lv = boost_library_version
    ver = lv.version
    ver.version = "boost-1.81.0"
    ver.save()
    cmd = Command()
    with (
        patch(
            "boost_library_docs_tracker.management.commands.run_boost_library_docs_tracker.fetcher.crawl_library_pages",
            return_value=[("https://x/", "body")],
        ),
        patch.object(cmd, "_resolve_library_version_id", return_value=None),
    ):
        n = cmd._process_library(
            version="boost-1.81.0",
            lib_key="algorithm",
            start_path=Path("."),
            use_local=False,
            dry_run=False,
            max_pages=10,
            boost_version_id=ver.pk,
        )
    assert n == 1


@pytest.mark.django_db
def test_save_pages_workspace_failure_continues(boost_library_version):
    lv = boost_library_version
    ver = lv.version
    ver.version = "boost-1.81.0"
    ver.save()
    cmd = Command()
    pages = [("https://a/", "x"), ("https://b/", "y")]
    with (
        patch(
            "boost_library_docs_tracker.management.commands.run_boost_library_docs_tracker.workspace.save_page",
            side_effect=[OSError("write fail"), None],
        ),
        patch(
            "boost_library_docs_tracker.management.commands.run_boost_library_docs_tracker.services.get_or_create_doc_content",
            return_value=(MagicMock(pk=1), "created"),
        ),
        patch(
            "boost_library_docs_tracker.management.commands.run_boost_library_docs_tracker.services.link_content_to_library_version",
        ),
    ):
        cmd._save_pages_to_workspace_and_db(
            version="boost-1.81.0",
            lib_name="algorithm",
            lib_version_id=lv.pk,
            boost_version_id=ver.pk,
            pages=pages,
        )


@pytest.mark.django_db
def test_save_pages_db_failure_continues(boost_library_version):
    lv = boost_library_version
    ver = lv.version
    ver.version = "boost-1.81.0"
    ver.save()
    cmd = Command()
    pages = [("https://a/", "body")]
    with (
        patch(
            "boost_library_docs_tracker.management.commands.run_boost_library_docs_tracker.workspace.save_page",
        ),
        patch(
            "boost_library_docs_tracker.management.commands.run_boost_library_docs_tracker.services.get_or_create_doc_content",
            side_effect=RuntimeError("db"),
        ),
    ):
        cmd._save_pages_to_workspace_and_db(
            version="boost-1.81.0",
            lib_name="algorithm",
            lib_version_id=lv.pk,
            boost_version_id=ver.pk,
            pages=pages,
        )


@pytest.mark.django_db
def test_sync_pinecone_import_skips():
    cmd = Command()
    import builtins

    orig = builtins.__import__

    def fake_import(name, globals_dict=None, locals_dict=None, fromlist=(), level=0):
        if name == "cppa_pinecone_sync.sync_api":
            raise ImportError("no pinecone")
        return orig(name, globals_dict, locals_dict, fromlist, level)

    with patch.object(builtins, "__import__", side_effect=fake_import):
        cmd._sync_pinecone()


@pytest.mark.django_db
def test_sync_pinecone_runtime_error():
    cmd = Command()
    mock_sync = MagicMock(side_effect=RuntimeError("api down"))
    fake_services = MagicMock(sync_to_pinecone=mock_sync)
    with patch.dict("sys.modules", {"cppa_pinecone_sync.sync_api": fake_services}):
        cmd._sync_pinecone()


@pytest.mark.django_db
def test_sync_pinecone_marks_success_and_failed_ids():
    cmd = Command()
    result = {
        "successful_source_ids": ["1", "nope", 3],
        "failed_ids": [4, "bad"],
        "upserted": 2,
        "total": 4,
        "failed_count": 1,
    }
    mock_sync = MagicMock(return_value=result)
    fake_services = MagicMock(sync_to_pinecone=mock_sync)
    with (
        patch.dict("sys.modules", {"cppa_pinecone_sync.sync_api": fake_services}),
        patch(
            "boost_library_docs_tracker.management.commands.run_boost_library_docs_tracker.services.set_doc_content_upserted_by_ids",
        ) as mark,
    ):
        cmd._sync_pinecone()
    assert mark.call_count == 2


@pytest.mark.django_db
def test_cleanup_extract_removes_zip_warns_on_oserror(boost_library_version, tmp_path):
    lv = boost_library_version
    ver = lv.version
    ver.version = "boost-1.81.0"
    ver.save()
    zip_path = tmp_path / "src.zip"
    zip_path.write_text("z", encoding="utf-8")
    extract_root = tmp_path / "extract"
    extract_root.mkdir()
    cmd = Command()
    with (
        patch.object(
            Command,
            "_prepare_local_source",
            return_value=(extract_root, zip_path),
        ),
        patch(
            "boost_library_docs_tracker.management.commands.run_boost_library_docs_tracker.fetcher.walk_library_html",
            return_value=[],
        ),
        patch(
            "boost_library_docs_tracker.management.commands.run_boost_library_docs_tracker.fetcher.delete_extract_dir",
        ),
        patch.object(Path, "unlink", side_effect=OSError("perm")),
    ):
        cmd._process_version(
            version="boost-1.81.0",
            library_filter=None,
            dry_run=False,
            max_pages=10,
            use_local=True,
            cleanup_extract=True,
        )


@pytest.mark.django_db
def test_collector_run_reraises_command_error():
    cmd = MagicMock()
    cmd._run.side_effect = CommandError("user error")
    collector = BoostLibraryDocsTrackerCollector(
        cmd,
        {
            "versions": [],
            "library": None,
            "dry_run": True,
            "skip_pinecone": True,
            "max_pages": 5,
            "use_local": False,
            "cleanup_extract": False,
        },
    )
    with pytest.raises(CommandError, match="user error"):
        collector.run()


@pytest.mark.django_db
def test_collector_run_wraps_generic_exception():
    cmd = MagicMock()
    cmd._run.side_effect = ValueError("oops")
    collector = BoostLibraryDocsTrackerCollector(
        cmd,
        {
            "versions": [],
            "library": None,
            "dry_run": True,
            "skip_pinecone": True,
            "max_pages": 5,
            "use_local": False,
            "cleanup_extract": False,
        },
    )
    with pytest.raises(CommandError, match="oops"):
        collector.run()


def test_collector_sync_pinecone_respects_flags():
    cmd = MagicMock()
    collector = BoostLibraryDocsTrackerCollector(
        cmd,
        {"dry_run": True, "skip_pinecone": False},
    )
    collector.sync_pinecone()
    cmd._sync_pinecone.assert_not_called()


@pytest.mark.django_db
def test_call_command_dry_run_skips_pinecone(boost_library_version):
    ver = boost_library_version.version
    ver.version = "boost-1.81.0"
    ver.save()
    buf = StringIO()
    from boost_library_docs_tracker.protocol_impl import LibraryDocsTrackerResult

    with (
        patch.object(
            Command,
            "_run",
            return_value=LibraryDocsTrackerResult.from_run(
                versions=1, pages=0, dry_run=True
            ),
        ) as run_mock,
        patch.object(Command, "_sync_pinecone") as sync_mock,
    ):
        call_command(
            "run_boost_library_docs_tracker",
            "--versions",
            "1.81.0",
            "--dry-run",
            stdout=buf,
        )
    run_mock.assert_called_once()
    sync_mock.assert_not_called()
