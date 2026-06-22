# Reddit Activity Tracker

## Overview

Ingests **Reddit subreddit submissions and comments** for configured targets into PostgreSQL and writes JSON snapshots under `WORKSPACE_DIR`. Supports **multiple subreddits**, per-subreddit **incremental cursors**, and optional **keyword filters** for high-traffic subs (for example `r/programming`).

**Docs:** [docs/service_api/reddit_activity_tracker.md](../docs/service_api/reddit_activity_tracker.md) · [docs/Schema.md, section 12 — Reddit Activity Tracker](../docs/Schema.md#12-reddit-activity-tracker-reddit_activity_tracker) · [`models.py`](models.py)

## Data workflow

`run_reddit_activity_tracker` chains **Reddit API fetch → PostgreSQL upsert → workspace JSON**. For each configured subreddit it resolves a submission and comment time window, fetches new posts and comments, optionally filters by keywords, then persists rows and writes user/submission/comment JSON files.

### Where we fetch data

**Reddit** via [`fetcher.py`](fetcher.py) (`RedditSession`): OAuth app credentials (`REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`) and/or session cookies (`REDDIT_SESSION_COOKIE`, `REDDIT_BEARER_TOKEN`). Targets come from `REDDIT_SUBREDDITS` or `--subreddits`. Rate limiting honors `REQUEST_INTERVAL` and `RATE_LIMIT_LOW_WATERMARK` (see `.env.example`).

### How data is saved to the database

Submissions and comments are upserted through [`services.py`](services.py) keyed by Reddit fullnames (`t3_*`, `t1_*`). Author rows are linked via `cppa_user_tracker` helpers when profile data is available. Incremental resume uses per-subreddit `created_utc` cursors in the database (or `REDDIT_DEFAULT_LOOKBACK_DAYS` on first run).

### Workspace layout

JSON files under `workspace/reddit_activity_tracker/`:

- `users/{username}.json`
- `submissions/{reddit_submission_id}.json`
- `comments/{reddit_comment_id}.json`

See [`workspace.py`](workspace.py).

### How content is published to GitHub

**Not applicable** — this app writes local workspace JSON only; it does not commit or push a context repository.

### How vectors sync to Pinecone

**Not applicable** today. If Reddit text should become searchable vectors, add a preprocessor and invoke [`cppa_pinecone_sync`](../cppa_pinecone_sync/README.md) per [docs/Pinecone_preprocess_guideline.md](../docs/Pinecone_preprocess_guideline.md).

## Configuration

| Setting | Description |
| --- | --- |
| `REDDIT_SUBREDDITS` | Comma-separated subreddit names (`r/` prefix optional). Default: `cpp,cpp_questions,programming`. |
| `REDDIT_SUBREDDIT_KEYWORD_FILTERS` | JSON object mapping subreddit → keyword list. Matching is case-insensitive substring on title/selftext (submissions) or body (comments). Default filters `programming` to Boost/C++ terms. |
| `REDDIT_DEFAULT_LOOKBACK_DAYS` | Days to look back when no DB cursor exists (default `30`). |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` / `REDDIT_USER_AGENT` | Reddit OAuth app credentials. |
| `REDDIT_SESSION_COOKIE` / `REDDIT_BEARER_TOKEN` | Optional session-based auth (see `.env.example`). |

Duplicates in `REDDIT_SUBREDDITS` or `--subreddits` are removed while preserving first-seen order.

## Common tasks

- Run the collector: `python manage.py run_reddit_activity_tracker --help`
- Override targets for one run: `python manage.py run_reddit_activity_tracker --subreddits cpp,cpp_questions`
- Backfill from a date: `python manage.py run_reddit_activity_tracker --since 2024-01-01`

## Main command: `run_reddit_activity_tracker`

Iterates configured subreddits, fetches submissions and comments in parallel time windows, applies keyword filters when configured, upserts DB rows, and writes workspace JSON.

| Option | Description |
| --- | --- |
| `--since` | Override start timestamp for **all** subreddits (`YYYY-MM-DD` or ISO datetime). Default: latest per-subreddit DB cursor, or lookback window if empty. |
| `--subreddits` | Comma-separated subreddit names (overrides `REDDIT_SUBREDDITS`). |

Scheduled via `config/boost_collector_schedule.yaml` under the `reddit` group.

## Management commands

| Command | Purpose |
| --- | --- |
| `run_reddit_activity_tracker` | Primary sync / collection command. |

Run `python manage.py COMMAND --help` for options.

## Tests

```bash
python -m pytest reddit_activity_tracker/tests/ -v
```

(from repo root; see root [README](../README.md#running-tests).)
