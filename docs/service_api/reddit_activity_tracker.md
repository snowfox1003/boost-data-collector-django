# reddit_activity_tracker.services

**Module path:** `reddit_activity_tracker.services`
**Description:** Service layer for Reddit submissions and comments. All creates/updates/deletes for this app's models must go through functions here.

**Type notation:** Model types refer to `reddit_activity_tracker.models`.

---
<!-- SERVICE_API:GENERATED:START -->

## Public API (generated)

| Function | Parameters | Return type | Summary |
| --- | --- | --- | --- |
| `get_latest_comment_created_utc` | *, subreddit: str \| None = None | int | Return max created_utc across comments, optionally scoped to one subreddit. |
| `get_latest_submission_created_utc` | *, subreddit: str \| None = None | int | Return max created_utc across submissions, optionally scoped to one subreddit. |
| `get_or_create_submission_stub` | submission_id: str, *, subreddit: str = 'cpp' | RedditSubmission | Ensure a submission row exists for FK when only a comment link_id is known. |
| `resolve_submission_for_comment` | comment_data: dict, submissions_by_id: dict[str, RedditSubmission] | RedditSubmission | Return the submission row for a period comment, creating a stub if needed. |
| `submission_id_from_link_id` | link_id: str | str \| None | — |
| `upsert_reddit_comment` | data: dict[str, Any], submission: RedditSubmission, *, session: RedditSession \| None = None | RedditComment | Update or create a comment keyed by reddit_comment_id. |
| `upsert_reddit_submission` | data: dict[str, Any], *, session: RedditSession \| None = None | RedditSubmission | Update or create a submission keyed by reddit_submission_id. |

<!-- SERVICE_API:GENERATED:END -->

## Related

- [Service API index](README.md)
- [Schema.md](../Schema.md) – Section 12: Reddit Activity Tracker.
- [CONTRIBUTING.md](../../CONTRIBUTING.md)
