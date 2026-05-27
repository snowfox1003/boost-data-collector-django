from concurrent.futures import Future
import json
import logging
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from github_activity_tracker.models import FileChangeStatus
from github_activity_tracker.sync import commits as sync_commits_mod
from github_activity_tracker.sync.commits import _process_commit_files


def test_process_commit_files_creates_files_and_changes():
    """_process_commit_files creates/updates GitHubFile and GitCommitFileChange for each file."""
    mock_repo = MagicMock()
    mock_commit = MagicMock()

    files = [
        {
            "filename": "added.txt",
            "status": "added",
            "additions": 10,
            "deletions": 0,
            "patch": "@@ -0,0 +1,10 @@...",
        },
        {
            "filename": "modified.txt",
            "status": "modified",
            "additions": 5,
            "deletions": 2,
        },
        {
            "filename": "deleted.txt",
            "status": "removed",
            "additions": 0,
            "deletions": 100,
        },
        {
            "filename": "new_name.txt",
            "previous_filename": "old_name.txt",
            "status": "renamed",
        },
        {
            "filename": "  spaced.txt  ",
            "status": " unknown_status ",
        },
        {
            "filename": "",  # Empty string, should be skipped
        },
        {
            "filename": None,  # None, should be skipped
        },
        {
            "filename": "   ",  # Whitespace, should be skipped
        },
    ]

    mock_github_file_1 = MagicMock()
    mock_github_file_2 = MagicMock()
    mock_github_file_3 = MagicMock()
    mock_old_file = MagicMock()
    mock_new_file = MagicMock()
    mock_github_file_5 = MagicMock()

    mock_create_file = MagicMock(
        side_effect=[
            (mock_github_file_1, True),
            (mock_github_file_2, False),
            (mock_github_file_3, False),
            (mock_old_file, False),
            (mock_new_file, True),
            (mock_github_file_5, True),
        ]
    )

    mock_add_change = MagicMock()
    mock_set_previous = MagicMock()

    with (
        patch(
            "github_activity_tracker.sync.commits.services.create_or_update_github_file",
            mock_create_file,
        ),
        patch(
            "github_activity_tracker.sync.commits.services.add_commit_file_change",
            mock_add_change,
        ),
        patch(
            "github_activity_tracker.sync.commits.services.set_github_file_previous_filename",
            mock_set_previous,
        ),
    ):
        _process_commit_files(mock_repo, mock_commit, files)

    assert mock_create_file.call_count == 6
    # added.txt
    mock_create_file.assert_any_call(mock_repo, "added.txt", is_deleted=False)
    # modified.txt
    mock_create_file.assert_any_call(mock_repo, "modified.txt", is_deleted=False)
    # deleted.txt
    mock_create_file.assert_any_call(mock_repo, "deleted.txt", is_deleted=True)
    # renamed: old then new
    mock_create_file.assert_any_call(mock_repo, "old_name.txt", is_deleted=False)
    mock_create_file.assert_any_call(mock_repo, "new_name.txt", is_deleted=False)
    # spaced.txt (trimmed)
    mock_create_file.assert_any_call(mock_repo, "spaced.txt", is_deleted=False)

    mock_set_previous.assert_called_once_with(mock_new_file, mock_old_file)

    assert mock_add_change.call_count == 5
    # added.txt
    mock_add_change.assert_any_call(
        mock_commit,
        mock_github_file_1,
        status="added",
        additions=10,
        deletions=0,
        patch="@@ -0,0 +1,10 @@...",
    )
    # modified.txt
    mock_add_change.assert_any_call(
        mock_commit,
        mock_github_file_2,
        status="modified",
        additions=5,
        deletions=2,
        patch="",
    )
    # deleted.txt
    mock_add_change.assert_any_call(
        mock_commit,
        mock_github_file_3,
        status="removed",
        additions=0,
        deletions=100,
        patch="",
    )
    # renamed (new_name.txt)
    mock_add_change.assert_any_call(
        mock_commit,
        mock_new_file,
        status="renamed",
        additions=0,
        deletions=0,
        patch="",
    )
    # spaced.txt (unknown_status becomes changed)
    mock_add_change.assert_any_call(
        mock_commit,
        mock_github_file_5,
        status=FileChangeStatus.CHANGED,
        additions=0,
        deletions=0,
        patch="",
    )


def test_process_commit_files_renamed_already_linked_does_not_call_set_previous():
    """When renamed file already has previous_filename_id set, set_github_file_previous_filename is not called."""
    mock_repo = MagicMock()
    mock_commit = MagicMock()

    files = [
        {
            "filename": "new.txt",
            "previous_filename": "old.txt",
            "status": "renamed",
        },
    ]

    mock_old_file = MagicMock()
    mock_old_file.id = 1
    mock_new_file = MagicMock()
    mock_new_file.previous_filename_id = 1  # Already linked to old_file

    mock_create_file = MagicMock(
        side_effect=[
            (mock_old_file, False),
            (mock_new_file, False),
        ]
    )
    mock_add_change = MagicMock()
    mock_set_previous = MagicMock()

    with (
        patch(
            "github_activity_tracker.sync.commits.services.create_or_update_github_file",
            mock_create_file,
        ),
        patch(
            "github_activity_tracker.sync.commits.services.add_commit_file_change",
            mock_add_change,
        ),
        patch(
            "github_activity_tracker.sync.commits.services.set_github_file_previous_filename",
            mock_set_previous,
        ),
    ):
        _process_commit_files(mock_repo, mock_commit, files)

    mock_set_previous.assert_not_called()
    mock_add_change.assert_called_once_with(
        mock_commit,
        mock_new_file,
        status="renamed",
        additions=0,
        deletions=0,
        patch="",
    )


def test_commit_author_name_and_email_variants():
    from github_activity_tracker.api_schemas import parse_commit

    assert sync_commits_mod._commit_author_name_and_email(
        parse_commit({"sha": "a" * 40, "commit": {}})
    ) == (
        "unknown",
        "",
    )
    d = {
        "sha": "b" * 40,
        "commit": {"author": {"name": None, "email": "  a@b.c "}},
    }
    assert sync_commits_mod._commit_author_name_and_email(parse_commit(d)) == (
        "unknown",
        "a@b.c",
    )
    d2 = {
        "sha": "c" * 40,
        "commit": {"committer": {"name": "  x  ", "email": ""}},
    }
    assert sync_commits_mod._commit_author_name_and_email(parse_commit(d2))[0] == "x"


@pytest.mark.django_db
def test_process_existing_commit_jsons_logs_on_bad_json(github_repository, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")

    with patch.object(
        sync_commits_mod,
        "iter_existing_commit_jsons",
        lambda owner, repo: [bad],
    ):
        n = sync_commits_mod._process_existing_commit_jsons(github_repository)
    assert n == 0


@pytest.mark.django_db
def test_process_existing_commit_jsons_success_then_unlink(
    github_repository,
    tmp_path,
):
    sha = "a" * 40
    body = {
        "sha": sha,
        "author": {
            "id": github_repository.owner_account.github_account_id,
            "login": github_repository.owner_account.username,
            "name": "Owner",
            "avatar_url": "",
        },
        "commit": {
            "message": "msg",
            "author": {"date": "2024-01-01T00:00:00Z", "name": "n", "email": "e@e"},
        },
        "files": [],
    }
    p = tmp_path / f"{sha}.json"
    p.write_text(json.dumps(body), encoding="utf-8")

    with (
        patch.object(
            sync_commits_mod,
            "iter_existing_commit_jsons",
            lambda owner, repo: [p],
        ),
        patch.object(sync_commits_mod, "save_commit_raw_source"),
    ):
        n = sync_commits_mod._process_existing_commit_jsons(github_repository)
    assert n == 1
    assert not p.exists()


@pytest.mark.django_db
def test_sync_commits_normal_fetch_and_persist(
    github_repository,
    tmp_path,
):
    sha = "b" * 40
    commit_data = {
        "sha": sha,
        "author": {
            "id": github_repository.owner_account.github_account_id,
            "login": github_repository.owner_account.username,
            "name": "Owner",
            "avatar_url": "",
        },
        "commit": {
            "message": "hello",
            "author": {"date": "2024-02-01T12:00:00Z"},
        },
        "files": [],
    }

    def fake_fetch(client, owner, repo, sd, ed, etag_cache=None):
        yield commit_data

    json_path = tmp_path / "staged.json"

    class _Exec:
        def submit(self, fn, *args, **kwargs):
            fut = Future()
            fut.set_result(None)
            return fut

        def shutdown(self, wait=True):
            return None

    with (
        patch.object(
            sync_commits_mod, "iter_existing_commit_jsons", lambda o, r: iter(())
        ),
        patch.object(sync_commits_mod, "get_github_client", return_value=MagicMock()),
        patch.object(
            sync_commits_mod.fetcher,
            "fetch_commits_from_github",
            fake_fetch,
        ),
        patch.object(
            sync_commits_mod.big_commit, "is_commit_truncated", return_value=False
        ),
        patch.object(sync_commits_mod, "get_commit_json_path", return_value=json_path),
        patch.object(sync_commits_mod, "RedisListETagCache", return_value=MagicMock()),
        patch.object(sync_commits_mod, "save_commit_raw_source"),
        patch.object(sync_commits_mod, "ThreadPoolExecutor", return_value=_Exec()),
    ):
        sync_commits_mod.sync_commits(github_repository)

    assert not json_path.exists()


@pytest.mark.django_db
def test_sync_commits_big_commit_submits_worker(
    github_repository,
    tmp_path,
):
    sha = "c" * 40
    commit_data = {
        "sha": sha,
        "parents": [{"sha": "d" * 40}],
        "author": {
            "id": github_repository.owner_account.github_account_id,
            "login": github_repository.owner_account.username,
            "name": "Owner",
            "avatar_url": "",
        },
        "commit": {"message": "big", "author": {"date": "2024-02-02T12:00:00Z"}},
        "files": [{"filename": "f.py"}] * 300,
    }
    out_json = tmp_path / "big_out.json"

    def fake_fetch(client, owner, repo, sd, ed, etag_cache=None):
        yield commit_data

    class _Exec:
        def __init__(self):
            self._futures: list = []

        def submit(self, fn, *args, **kwargs):
            fn(*args, **kwargs)
            fut = Future()
            fut.set_result(None)
            self._futures.append(fut)
            return fut

        def shutdown(self, wait=True):
            return None

    with (
        patch.object(
            sync_commits_mod, "iter_existing_commit_jsons", lambda o, r: iter(())
        ),
        patch.object(sync_commits_mod, "get_github_client", return_value=MagicMock()),
        patch.object(
            sync_commits_mod.fetcher,
            "fetch_commits_from_github",
            fake_fetch,
        ),
        patch.object(
            sync_commits_mod.big_commit, "is_commit_truncated", return_value=True
        ),
        patch.object(
            sync_commits_mod.big_commit,
            "get_full_commit_files",
            return_value=[{"filename": "only.py", "status": "added"}],
        ),
        patch.object(sync_commits_mod, "get_commit_json_path", return_value=out_json),
        patch.object(sync_commits_mod, "RedisListETagCache", return_value=MagicMock()),
        patch.object(
            sync_commits_mod, "ThreadPoolExecutor", side_effect=lambda *a, **k: _Exec()
        ),
        patch.object(
            sync_commits_mod, "_process_existing_commit_jsons", return_value=0
        ),
    ):
        sync_commits_mod.sync_commits(github_repository)

    assert out_json.is_file()


@pytest.mark.django_db
def test_sync_commits_big_worker_get_files_falls_back(
    github_repository,
    tmp_path,
):
    sha = "e" * 40
    commit_data = {
        "sha": sha,
        "parents": [],
        "author": {
            "id": github_repository.owner_account.github_account_id,
            "login": github_repository.owner_account.username,
            "name": "Owner",
            "avatar_url": "",
        },
        "commit": {"message": "m", "author": {"date": "2024-02-03T12:00:00Z"}},
        "files": [{"filename": "x", "status": "added"}],
    }
    out_json = tmp_path / "fb.json"

    with (
        patch.object(
            sync_commits_mod.big_commit,
            "get_full_commit_files",
            side_effect=RuntimeError("git fail"),
        ),
        patch.object(sync_commits_mod, "get_commit_json_path", return_value=out_json),
    ):
        sync_commits_mod._process_big_commit_worker(
            github_repository.owner_account.username,
            github_repository.repo_name,
            commit_data,
        )
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["sha"] == sha
    assert len(payload["files"]) == 1


@pytest.mark.django_db
def test_sync_commits_skips_fetch_item_without_sha(github_repository, tmp_path):
    def fake_fetch(client, owner, repo, sd, ed, etag_cache=None):
        yield {"sha": None}
        yield {}

    class _Exec:
        def submit(self, *a, **k):
            fut = Future()
            fut.set_result(None)
            return fut

        def shutdown(self, wait=True):
            return None

    with (
        patch.object(
            sync_commits_mod, "iter_existing_commit_jsons", lambda o, r: iter(())
        ),
        patch.object(sync_commits_mod, "get_github_client", return_value=MagicMock()),
        patch.object(
            sync_commits_mod.fetcher,
            "fetch_commits_from_github",
            fake_fetch,
        ),
        patch.object(sync_commits_mod, "RedisListETagCache", return_value=MagicMock()),
        patch.object(sync_commits_mod, "ThreadPoolExecutor", return_value=_Exec()),
        patch.object(
            sync_commits_mod,
            "_process_commit_data",
        ) as mock_process_commit_data,
    ):
        sync_commits_mod.sync_commits(github_repository)

    mock_process_commit_data.assert_not_called()


@pytest.mark.django_db
def test_sync_commits_raises_rate_limit(github_repository):
    from core.operations.github_ops.client import RateLimitException

    def boom(*a, **k):
        raise RateLimitException("rl")

    class _Exec:
        def submit(self, *a, **k):
            return Future()

        def shutdown(self, wait=True):
            return None

    with (
        patch.object(
            sync_commits_mod, "iter_existing_commit_jsons", lambda o, r: iter(())
        ),
        patch.object(sync_commits_mod, "get_github_client", return_value=MagicMock()),
        patch.object(sync_commits_mod.fetcher, "fetch_commits_from_github", boom),
        patch.object(sync_commits_mod, "RedisListETagCache", return_value=MagicMock()),
        patch.object(sync_commits_mod, "ThreadPoolExecutor", return_value=_Exec()),
    ):
        with pytest.raises(RateLimitException):
            sync_commits_mod.sync_commits(github_repository)


@pytest.mark.django_db
def test_sync_commits_future_result_exception_logged(
    github_repository,
    tmp_path,
    caplog,
):
    sha = "f" * 40
    commit_data = {
        "sha": sha,
        "author": {
            "id": github_repository.owner_account.github_account_id,
            "login": github_repository.owner_account.username,
            "name": "Owner",
            "avatar_url": "",
        },
        "commit": {"message": "m", "author": {"date": "2024-02-04T12:00:00Z"}},
        "files": [{"filename": "z", "status": "added"}] * 300,
    }

    def fake_fetch(client, owner, repo, sd, ed, etag_cache=None):
        yield commit_data

    fut = Future()
    fut.set_exception(RuntimeError("worker boom"))

    class _Exec:
        def submit(self, *a, **k):
            return fut

        def shutdown(self, wait=True):
            return None

    with (
        patch.object(
            sync_commits_mod, "iter_existing_commit_jsons", lambda o, r: iter(())
        ),
        patch.object(sync_commits_mod, "get_github_client", return_value=MagicMock()),
        patch.object(
            sync_commits_mod.fetcher,
            "fetch_commits_from_github",
            fake_fetch,
        ),
        patch.object(
            sync_commits_mod.big_commit, "is_commit_truncated", return_value=True
        ),
        patch.object(sync_commits_mod, "RedisListETagCache", return_value=MagicMock()),
        patch.object(sync_commits_mod, "ThreadPoolExecutor", return_value=_Exec()),
        patch.object(
            sync_commits_mod, "_process_existing_commit_jsons", return_value=0
        ),
        caplog.at_level(logging.ERROR, logger="github_activity_tracker.sync.commits"),
    ):
        sync_commits_mod.sync_commits(github_repository)

    logged = " ".join(r.message for r in caplog.records)
    assert "Big commit task" in logged and "worker boom" in logged


@pytest.mark.django_db
def test_process_commit_data_unknown_author_and_files(github_repository):
    sha = "1" * 40
    data = {
        "sha": sha,
        "commit": {
            "message": "m",
            "author": {"date": "2024-01-05T00:00:00Z", "name": None, "email": "a@b"},
        },
        "files": [{"filename": "x.py", "status": "added", "additions": 1}],
    }
    sync_commits_mod._process_commit_data(github_repository, data)
    assert github_repository.commits.filter(commit_hash=sha).exists()


@pytest.mark.django_db
def test_sync_commits_start_date_from_last_commit(github_repository):
    from github_activity_tracker.models import GitCommit

    GitCommit.objects.create(
        repo=github_repository,
        account=github_repository.owner_account,
        commit_hash="0" * 40,
        comment="",
        commit_at=datetime(2024, 7, 1, tzinfo=timezone.utc),
    )
    mock_fetch = MagicMock(return_value=[])

    class _Exec:
        def submit(self, *a, **k):
            fut = Future()
            fut.set_result(None)
            return fut

        def shutdown(self, wait=True):
            return None

    with (
        patch.object(
            sync_commits_mod, "iter_existing_commit_jsons", lambda o, r: iter(())
        ),
        patch.object(sync_commits_mod, "get_github_client", return_value=MagicMock()),
        patch.object(
            sync_commits_mod.fetcher,
            "fetch_commits_from_github",
            mock_fetch,
        ),
        patch.object(sync_commits_mod, "RedisListETagCache", return_value=MagicMock()),
        patch.object(sync_commits_mod, "ThreadPoolExecutor", return_value=_Exec()),
    ):
        sync_commits_mod.sync_commits(github_repository)

    start = mock_fetch.call_args[0][3]
    assert start == datetime(2024, 7, 1, 0, 0, 1, tzinfo=timezone.utc)


@pytest.mark.django_db
def test_sync_commits_unexpected_exception(github_repository):
    class _Exec:
        def submit(self, *a, **k):
            fut = Future()
            fut.set_result(None)
            return fut

        def shutdown(self, wait=True):
            return None

    with (
        patch.object(
            sync_commits_mod, "iter_existing_commit_jsons", lambda o, r: iter(())
        ),
        patch.object(sync_commits_mod, "get_github_client", return_value=MagicMock()),
        patch.object(
            sync_commits_mod.fetcher,
            "fetch_commits_from_github",
            side_effect=ValueError("unexpected"),
        ),
        patch.object(sync_commits_mod, "RedisListETagCache", return_value=MagicMock()),
        patch.object(sync_commits_mod, "ThreadPoolExecutor", return_value=_Exec()),
    ):
        with pytest.raises(ValueError, match="unexpected"):
            sync_commits_mod.sync_commits(github_repository)


@pytest.mark.django_db
def test_process_big_commit_worker_primary_write_fails_then_fallback():
    sha = "2" * 40
    commit_data = {
        "sha": sha,
        "parents": [],
        "commit": {"message": "m", "author": {"date": "2024-01-01T00:00:00Z"}},
        "files": [{"filename": "f", "status": "added"}],
    }
    primary = MagicMock()
    primary.parent.mkdir = MagicMock()
    primary.write_text = MagicMock(side_effect=OSError("disk full"))
    fallback = MagicMock()
    fallback.parent.mkdir = MagicMock()
    fallback.write_text = MagicMock()

    with (
        patch.object(
            sync_commits_mod,
            "get_commit_json_path",
            side_effect=[primary, fallback],
        ),
        patch.object(
            sync_commits_mod.big_commit,
            "get_full_commit_files",
            return_value=[{"filename": "g.py", "status": "added"}],
        ),
    ):
        sync_commits_mod._process_big_commit_worker("o", "r", commit_data)

    fallback.write_text.assert_called_once()


@pytest.mark.django_db
def test_sync_commits_logs_existing_json_count(github_repository, caplog):
    class _Exec:
        def submit(self, *a, **k):
            fut = Future()
            fut.set_result(None)
            return fut

        def shutdown(self, wait=True):
            return None

    with (
        patch.object(
            sync_commits_mod, "_process_existing_commit_jsons", return_value=4
        ),
        patch.object(sync_commits_mod, "get_github_client", return_value=MagicMock()),
        patch.object(
            sync_commits_mod.fetcher,
            "fetch_commits_from_github",
            lambda *a, **k: iter(()),
        ),
        patch.object(sync_commits_mod, "RedisListETagCache", return_value=MagicMock()),
        patch.object(sync_commits_mod, "ThreadPoolExecutor", return_value=_Exec()),
        caplog.at_level(logging.INFO, logger="github_activity_tracker.sync.commits"),
    ):
        sync_commits_mod.sync_commits(github_repository)

    logged = " ".join(r.message for r in caplog.records)
    assert "processed 4 existing commit JSON" in logged


@pytest.mark.django_db
def test_process_big_commit_worker_fallback_write_also_fails():
    sha = "3" * 40
    commit_data = {
        "sha": sha,
        "parents": [],
        "commit": {"message": "m", "author": {"date": "2024-01-01T00:00:00Z"}},
        "files": [],
    }
    primary = MagicMock()
    primary.parent.mkdir = MagicMock()
    primary.write_text = MagicMock(side_effect=OSError("primary fail"))
    fallback = MagicMock()
    fallback.parent.mkdir = MagicMock()
    fallback.write_text = MagicMock(side_effect=OSError("fallback fail"))

    with (
        patch.object(
            sync_commits_mod,
            "get_commit_json_path",
            side_effect=[primary, fallback],
        ),
        patch.object(
            sync_commits_mod.big_commit,
            "get_full_commit_files",
            return_value=[{"filename": "z.py", "status": "added"}],
        ),
    ):
        sync_commits_mod._process_big_commit_worker("o", "r", commit_data)

    fallback.write_text.assert_called_once()
