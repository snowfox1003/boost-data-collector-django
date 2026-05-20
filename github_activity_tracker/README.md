# GitHub Activity Tracker

## Overview

Collects **GitHub activity** (commits, issues, PRs, files) for configured repositories into PostgreSQL and uses the shared **`workspace/`** tree for raw JSON before ingestion. Behavior is sensitive to **rate limits**, **multiple GitHub tokens**, and **workspace layout**—see [docs/Workspace.md](../docs/Workspace.md) and [docs/operations/github.md](../docs/operations/github.md).

**There is no `run_github_activity_tracker` (or similar) in this app.** Scheduled GitHub ingest is started by **other apps’** management commands, which import this package’s sync code and models—for example **`run_boost_github_activity_tracker`** in [`boost_library_tracker`](../boost_library_tracker/README.md) and **`run_clang_github_tracker`** in [`clang_github_tracker`](../clang_github_tracker/README.md). This repo’s YAML schedule and docs refer to those commands, not a `github_activity_tracker`-prefixed runner.

## Data workflow

This app owns the **GitHub activity models and sync helpers** (`sync_github` and related) that **parent collectors** invoke; it does **not** register its own primary collector command. Routine Boost ingest is driven from [`boost_library_tracker`](../boost_library_tracker/README.md); LLVM/Clang activity from [`clang_github_tracker`](../clang_github_tracker/README.md). Service details: [docs/service_api/github_activity_tracker.md](../docs/service_api/github_activity_tracker.md). See also [docs/Architecture_data_flow.md](../docs/Architecture_data_flow.md).

### Where we fetch data

**GitHub** (REST/GraphQL via `core.operations.github_ops`) when a **calling app’s** command runs `sync_github` (or equivalent) for a configured owner/repo window—**not** via a standalone `manage.py` entrypoint defined only in `github_activity_tracker`. Tokens follow the project’s `GITHUB_TOKEN` / `GITHUB_TOKENS_SCRAPING` / `GITHUB_TOKEN_WRITE` conventions (root [README](../README.md)).

### How data is saved to the database

Normalized **commits, issues, PRs, and file-change rows** are upserted into this app’s PostgreSQL models. **Raw JSON** for replay, rate-limit recovery, and backfills is written under `WORKSPACE_DIR/github_activity_tracker/` (layout details in [docs/Workspace.md](../docs/Workspace.md)). **References:** [docs/Schema.md, section 2 — GitHub Activity Tracker](../docs/Schema.md#2-github-activity-tracker) · [`models.py`](models.py) · [docs/service_api/github_activity_tracker.md](../docs/service_api/github_activity_tracker.md).

### How content is published to GitHub

**Not in this app by itself.** Markdown generation and repository uploads are implemented in **calling collectors** (for example `run_boost_github_activity_tracker`, `run_clang_github_tracker`) using `core.operations.md_ops` and `github_ops`.

### How vectors sync to Pinecone

**Indirect.** [`preprocessors/github_preprocess.py`](preprocessors/github_preprocess.py) builds document dicts for `cppa_pinecone_sync.sync.sync_to_pinecone`. Upserts are invoked from those parent commands when Pinecone sync is enabled—not from the maintenance commands in this README. See [docs/Pinecone_preprocess_guideline.md](../docs/Pinecone_preprocess_guideline.md).

## Common tasks

- After changing workspace paths or repo list: review migrations and maintenance commands under `management/commands/` (layout migrations, backfills).
- Token setup: `GITHUB_TOKEN`, `GITHUB_TOKENS_SCRAPING`, `GITHUB_TOKEN_WRITE` in `.env` (see root README **GitHub tokens**).

## Main commands in this app

This package does **not** ship a primary `run_github_*` collector for the YAML schedule. Boost flows use **`run_boost_github_activity_tracker`** ([`boost_library_tracker`](../boost_library_tracker/README.md)); Clang flows use **`run_clang_github_tracker`** ([`clang_github_tracker`](../clang_github_tracker/README.md)). The commands documented below are **maintenance** utilities only (`migrate_workspace_layout`, `backfill_300_file_commits`).

### `migrate_workspace_layout`

Rewrites files under `WORKSPACE_DIR/github_activity_tracker/` from the legacy tree (`<owner>/commits/<repo>/…`) into `<owner>/<repo>/commits|issues|prs/`.

| Option | Description |
| --- | --- |
| `--dry-run` | Print planned moves only; do not modify files. |

### `backfill_300_file_commits`

Finds commits with exactly **300** file-change rows (GitHub API truncation), refetches full file lists via git, and updates the DB.

| Option | Description |
| --- | --- |
| `--dry-run` | List commits that would update; no DB writes. |
| `--limit` | Process at most **N** commits (`0` = no limit). |

## Package

- **Django app label:** `github_activity_tracker`
- **Path (from repo root):** `github_activity_tracker/`
- **Registration:** Listed under `INSTALLED_APPS` in [`config/settings.py`](../config/settings.py) as `github_activity_tracker`.

## Management commands

| Command | Description |
| --- | --- |
| `backfill_300_file_commits` | Backfill commits that have exactly 300 file changes (API truncation). |
| `migrate_workspace_layout` | Migrate workspace/github_activity_tracker from the legacy layout to the app layout. |

Run `python manage.py <command> --help` for options.

## Tests

Typical invocation (from repo root, after [README prerequisites](../README.md#running-tests)):

```bash
python -m pytest github_activity_tracker/tests/ -v
```
