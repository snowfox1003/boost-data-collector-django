"""Tests for github_activity_tracker.sync_api cross-app surface."""

from github_activity_tracker import sync_api


def test_sync_api_exports_fetcher():
    assert sync_api.fetcher is not None


def test_sync_api_exports_normalize_helpers():
    assert callable(sync_api.normalize_issue_json)
    assert callable(sync_api.normalize_pr_json)


def test_sync_api_exports_raw_source_helpers():
    assert callable(sync_api.save_commit_raw_source)
    assert callable(sync_api.save_issue_raw_source)
    assert callable(sync_api.save_pr_raw_source)


def test_sync_api_exports_workspace_paths():
    assert callable(sync_api.get_commit_json_path)
    assert callable(sync_api.get_raw_source_issue_path)
    assert callable(sync_api.iter_existing_pr_jsons)


def test_sync_api_exports_preprocess_builders():
    assert callable(sync_api.build_issue_document)
    assert callable(sync_api.build_pr_document)


def test_sync_api_exports_batch_preprocessors():
    from github_activity_tracker.preprocessors.github_preprocess import (
        preprocess_all_issues,
        preprocess_all_prs,
    )

    assert sync_api.preprocess_all_issues is preprocess_all_issues
    assert sync_api.preprocess_all_prs is preprocess_all_prs


def test_sync_api_exports_sync_github():
    from github_activity_tracker.sync import sync_github

    assert sync_api.sync_github is sync_github


def test_sync_api_exports_github_sync_tracker_result():
    from github_activity_tracker.protocol_impl import GitHubSyncTrackerResult

    assert sync_api.GitHubSyncTrackerResult is GitHubSyncTrackerResult
