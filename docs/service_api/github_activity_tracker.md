# github_activity_tracker.services

**Module path:** `github_activity_tracker.services`
**Description:** Repos, languages, licenses, issues, pull requests, assignees, and labels. Single place for all writes to github_activity_tracker models.

**Type notation:** Model types refer to `github_activity_tracker.models`. Cross-app: `GitHubAccount` is `cppa_user_tracker.models.GitHubAccount`.

---
<!-- SERVICE_API:GENERATED:START -->

## Public API (generated)

| Function | Parameters | Return type | Summary |
| --- | --- | --- | --- |
| `add_commit_file_change` | commit: GitCommit, github_file: GitHubFile, status: str, additions: int = 0, deletions: int = 0, patch: str = '' | tuple[GitCommitFileChange, bool] | Add or update a file change for a commit. If exists, updates status, additions, deletions, patch. Returns (file_change, created). |
| `add_issue_assignee` | issue: Issue, account: GitHubAccount | None | Add an assignee to an issue (M2M). Idempotent. |
| `add_issue_label` | issue: Issue, label_name: str | tuple[IssueLabel, bool] | Add a label to an issue. Returns (IssueLabel, created). |
| `add_pr_assignee` | pr: PullRequest, account: GitHubAccount | None | Add an assignee to a PR (M2M). Idempotent. |
| `add_pull_request_label` | pr: PullRequest, label_name: str | tuple[PullRequestLabel, bool] | Add a label to a pull request. Returns (PullRequestLabel, created). |
| `add_repo_language` | repo: GitHubRepository, language: Language, line_count: int = 0 | tuple[RepoLanguage, bool] | Add or update a repo–language link with line_count. If exists, updates line_count. Returns (RepoLanguage, created). |
| `add_repo_license` | repo: GitHubRepository, license_obj: License | None | Add a License to a repo (M2M). Idempotent. |
| `create_or_update_commit` | repo: GitHubRepository, account: GitHubAccount, commit_hash: str, comment: str = '', commit_at: Optional[datetime] = None | tuple[GitCommit, bool] | Create or update a GitCommit by repo + commit_hash. Returns (commit, created). |
| `create_or_update_created_repos_by_language` | language: Language, year: int, all_repos: int, significant_repos: int | tuple[CreatedReposByLanguage, bool] | Create or update CreatedReposByLanguage for (language, year). |
| `create_or_update_github_file` | repo: GitHubRepository, filename: str, is_deleted: bool = False | tuple[GitHubFile, bool] | Create or update a GitHubFile by repo + filename. Returns (file, created). |
| `create_or_update_issue` | repo: GitHubRepository, account: GitHubAccount, issue_number: int, issue_id: int, title: str = '', body: str = '', state: str = IssueState.OPEN, state_reason: str = '', issue_created_at: Optional[datetime] = None, issue_updated_at: Optional[datetime] = None, issue_closed_at: Optional[datetime] = None | tuple[Issue, bool] | Create or update an Issue by issue_id. Returns (issue, created). |
| `create_or_update_issue_comment` | issue: Issue, account: GitHubAccount, issue_comment_id: int, body: str = '', issue_comment_created_at: Optional[datetime] = None, issue_comment_updated_at: Optional[datetime] = None | tuple[IssueComment, bool] | Create or update an IssueComment by issue_comment_id. Returns (comment, created). |
| `create_or_update_pr_comment` | pr: PullRequest, account: GitHubAccount, pr_comment_id: int, body: str = '', pr_comment_created_at: Optional[datetime] = None, pr_comment_updated_at: Optional[datetime] = None | tuple[PullRequestComment, bool] | Create or update a PullRequestComment by pr_comment_id. Returns (comment, created). |
| `create_or_update_pr_review` | pr: PullRequest, account: GitHubAccount, pr_review_id: int, body: str = '', in_reply_to_id: Optional[int] = None, pr_review_created_at: Optional[datetime] = None, pr_review_updated_at: Optional[datetime] = None | tuple[PullRequestReview, bool] | Create or update a PullRequestReview by pr_review_id. Returns (review, created). |
| `create_or_update_pull_request` | repo: GitHubRepository, account: GitHubAccount, pr_number: int, pr_id: int, title: str = '', body: str = '', state: str = PullRequestState.OPEN, head_hash: str = '', base_hash: str = '', pr_created_at: Optional[datetime] = None, pr_updated_at: Optional[datetime] = None, pr_merged_at: Optional[datetime] = None, pr_closed_at: Optional[datetime] = None | tuple[PullRequest, bool] | Create or update a PullRequest by pr_id. Returns (pr, created). |
| `ensure_repository_owner` | repo: GitHubRepository, owner_account: GitHubAccount | None | Ensure repo has owner_account set (fixes rows with null owner_account_id). |
| `get_or_create_language` | name: str | tuple[Language, bool] | Get or create a Language by name. Returns (Language, created). |
| `get_or_create_license` | name: str, spdx_id: str = '', url: str = '' | tuple[License, bool] | Get or create a License by name. If exists, updates spdx_id and url. Returns (License, created). |
| `get_or_create_repository` | owner_account: GitHubAccount, repo_name: str, **defaults: Any | tuple[GitHubRepository, bool] | Get or create a GitHubRepository by owner_account and repo_name. If exists, updates fields in defaults. Returns (repo, created). |
| `remove_issue_assignee` | issue: Issue, account: GitHubAccount | None | Remove an assignee from an issue. |
| `remove_issue_label` | issue: Issue, label_name: str | None | Remove a label from an issue. |
| `remove_pr_assignee` | pr: PullRequest, account: GitHubAccount | None | Remove an assignee from a PR. |
| `remove_pull_request_label` | pr: PullRequest, label_name: str | None | Remove a label from a pull request. |
| `remove_repo_license` | repo: GitHubRepository, license_obj: License | None | Remove a License from a repo. |
| `set_github_file_previous_filename` | github_file: GitHubFile, previous_file: GitHubFile | None | Set the previous_filename reference for a renamed file. |
| `update_repo_language_line_count` | repo: GitHubRepository, language: Language, line_count: int | RepoLanguage | Update line_count for an existing repo–language link. |

<!-- SERVICE_API:GENERATED:END -->

## Not yet in API

- GitCommit, GitHubFile, GitCommitFileChange: add `create_commit`, `create_github_file`, `add_commit_file_change` when needed.
- IssueComment, PullRequestReview, PullRequestComment: add `create_issue_comment`, `create_pr_review`, `create_pr_comment` when needed.

---

## Sync / orchestration (not a service)

To sync a repo from GitHub (read last updated from DB, fetch from GitHub, save via the services above), use the **sync** package—it is orchestration, not a write:

| Entry point | Parameter types | Return type | Description |
|-------------|-----------------|-------------|-------------|
| `sync_github(repo)` | `repo: GitHubRepository` | `None` | Run full sync for one repo: repos (metadata), then commits, issues, pull requests. Accepts `GitHubRepository` or a subclass (e.g. `BoostLibraryRepository`). Raises `ValueError` if `repo` is `None`. |

**Module:** `github_activity_tracker.sync`
**Usage:** `from github_activity_tracker.sync import sync_github` then `sync_github(repo)`.

## Cross-app orchestration API

Other tracker apps that reuse GitHub fetch, raw JSON staging, normalization, or Pinecone
document builders must import from **`github_activity_tracker.sync_api`** only — not
`fetcher`, `sync.*`, `workspace`, or `preprocessors` directly.

**Module:** `github_activity_tracker.sync_api`

Exports include: `fetcher`, `normalize_issue_json`, `normalize_pr_json`,
`save_commit_raw_source`, `save_issue_raw_source`, `save_pr_raw_source`,
workspace path helpers (`get_commit_json_path`, `get_raw_source_issue_path`, …),
`iter_existing_*_jsons`, `build_issue_document`, `build_pr_document`.

---

## Related

- [Service API index](README.md)
- [CONTRIBUTING](../../CONTRIBUTING.md)
- [Schema](../Schema.md)
