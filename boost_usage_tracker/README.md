# Boost Usage Tracker

## Overview

Collects **Boost library usage signals** (e.g. repository metadata tied to Boost) and runs periodic **database update** commands. Commands split between the main tracker run and smaller `run_update_*` jobs.

## Data workflow

Commands here focus on **GitHub-derived usage signals** (repository content, stars) and periodic **DB maintenance** helpers. Service details: [docs/service_api/boost_usage_tracker.md](../docs/service_api/boost_usage_tracker.md). See [docs/Architecture_data_flow.md](../docs/Architecture_data_flow.md) for how this fits the wider platform.

### Where we fetch data

**GitHub** search and repository APIs (via `core.operations.github_ops` patterns) for `run_boost_usage_tracker` tasks such as **`monitor_content`** and **`monitor_stars`**, within the date and star thresholds you pass on the CLI.

### How data is saved to the database

Usage signals and discovered repositories are upserted into this app’s models (`run_boost_usage_tracker`, `run_update_created_repos_by_language`). **`run_update_db`** performs targeted refreshes or housekeeping defined in that command’s implementation. Optional CSV or staging paths may use `WORKSPACE_DIR` for exports. **References:** [docs/Schema.md, section 4 — Boost Usage Tracker](../docs/Schema.md#4-boost-usage-tracker) · [`models.py`](models.py) · [docs/service_api/boost_usage_tracker.md](../docs/service_api/boost_usage_tracker.md).

### How content is published to GitHub

**Not applicable.** This app records analytics in PostgreSQL; it does not push Markdown repos or open PRs as part of its collectors.

### How vectors sync to Pinecone

**Not applicable.** There is no Pinecone sync phase in this app. Other collectors follow [docs/Pinecone_preprocess_guideline.md](../docs/Pinecone_preprocess_guideline.md) when they upsert usage-adjacent text.

## Common tasks

- Full tracker: `python manage.py run_boost_usage_tracker --help`
- DB refresh helpers: `run_update_db`, `run_update_created_repos_by_language` (see the **Management commands** section below).

## Main command: `run_boost_usage_tracker`

Runs **monitor_content** (repo/content signals) and/or **monitor_stars** (monthly star counts) inside one collector invocation unless `--task` narrows it.

| Option | Description |
| --- | --- |
| `--task` | `monitor_content` \| `monitor_stars` — run only that task. **Default:** both, in order (`monitor_content` then `monitor_stars`). |
| `--since` | `YYYY-MM-DD` lower bound for `monitor_content` (default: **yesterday**). |
| `--until` | `YYYY-MM-DD` upper bound for `monitor_content` (default: **today**). |
| `--min-stars` | Minimum stars filter for `monitor_stars` (default **10**). |
| `--dry-run` | Log actions only; no DB changes. |

## Package

- **Django app label:** `boost_usage_tracker`
- **Path (from repo root):** `boost_usage_tracker/`
- **Registration:** Listed under `INSTALLED_APPS` in [`config/settings.py`](../config/settings.py) as `boost_usage_tracker`.

## Management commands

| Command | Description |
| --- | --- |
| `run_boost_usage_tracker` | Primary collector: **`monitor_content`** searches GitHub for C++ repos pushed in a date range and records Boost `#include` usage; **`monitor_stars`** scans highly starred C++ repos for new candidates. Updates **`BoostExternalRepository`**, **`BoostUsage`**, and related rows (see command `help`). |
| `run_update_created_repos_by_language` | Calls the GitHub API to count **new repositories per language per year** (star threshold configurable) and upserts **`github_activity_tracker.CreatedReposByLanguage`**. |
| `run_update_db` | **Bulk import / repair** from JSON or CSV under `WORKSPACE_DIR` (or `--source`): **`--target`** chooses the pipeline (`github_account`, `repository`, `githubfile`, `boostusage`) to refresh GitHub accounts, repos, files, or usage rows. |

Run `python manage.py <command> --help` for options.

## Tests

Typical invocation (from repo root, after [README prerequisites](../README.md#running-tests)):

```bash
python -m pytest boost_usage_tracker/tests/ -v
```
