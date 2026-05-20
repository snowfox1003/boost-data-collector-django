# Boost Library Usage Dashboard

## Overview

Maintains **usage and dashboard-oriented** data for Boost libraries (aggregates and refresh commands consumed by reporting). Command surface is small; most business rules live in services and models.

## Data workflow

`run_boost_library_usage_dashboard` **reads metrics already stored in PostgreSQL**, generates human-readable reports (Markdown/HTML), and can **publish** static assets to a GitHub repository used for dashboards. Dashboard metrics align with **Boost usage** catalog data: [docs/Schema.md, section 4 — Boost Usage Tracker](../docs/Schema.md#4-boost-usage-tracker). Models are re-exported from **`boost_usage_tracker`** — see [`models.py`](models.py) and [docs/service_api/boost_usage_tracker.md](../docs/service_api/boost_usage_tracker.md).

### Where we fetch data

**Primarily PostgreSQL** (aggregated usage and library statistics populated by other collectors). The publish phase may **clone/pull** the target GitHub repo using `core.operations.github_ops.git_ops` when publishing is enabled.

### How data is saved to the database

The command **refreshes dashboard-oriented tables** and derived aggregates defined in this app’s models and services so downstream reporting stays current. Local **HTML/Markdown** outputs may be written under `WORKSPACE_DIR` before publish. **References:** [docs/Schema.md, section 4 — Boost Usage Tracker](../docs/Schema.md#4-boost-usage-tracker) · [`models.py`](models.py) (re-exports **`boost_usage_tracker`**) · [docs/service_api/boost_usage_tracker.md](../docs/service_api/boost_usage_tracker.md).

### How content is published to GitHub

When `--skip-publish` is **not** set, [`publisher.py`](publisher.py) prepares the repo and **pushes** generated HTML (and related assets) to **`BOOST_LIBRARY_USAGE_DASHBOARD_PUBLISH_*`** (overridable with `--owner`, `--repo`, `--branch`). A valid **`GITHUB_TOKEN_WRITE`** (or configured fallback) is required for git operations.

### How vectors sync to Pinecone

**Not applicable** for this app today. Search vectors for docs or discussions come from other pipelines ([`cppa_pinecone_sync`](../cppa_pinecone_sync/README.md), docs tracker, Slack, and so on).

## Common tasks

- Run the tracker: `python manage.py run_boost_library_usage_dashboard --help`.
- Schema: [docs/Schema.md, section 4 — Boost Usage Tracker](../docs/Schema.md#4-boost-usage-tracker).

## Main command: `run_boost_library_usage_dashboard`

Builds metrics from PostgreSQL, renders HTML, and optionally publishes to the configured GitHub repo.

| Option | Description |
| --- | --- |
| `--skip-collect` | Skip PostgreSQL collection + Markdown report generation. |
| `--skip-render` | Skip HTML rendering. |
| `--skip-publish` | Skip push to GitHub. |
| `--owner` | Publish repo owner (overrides `BOOST_LIBRARY_USAGE_DASHBOARD_PUBLISH_OWNER`). |
| `--repo` | Publish repo name (overrides `BOOST_LIBRARY_USAGE_DASHBOARD_PUBLISH_REPO`). |
| `--branch` | Publish branch (overrides `BOOST_LIBRARY_USAGE_DASHBOARD_PUBLISH_BRANCH`; default `main`). |

## Management commands

| Command | Purpose |
| --- | --- |
| `run_boost_library_usage_dashboard` | Primary scheduled job for this app. |

Run `python manage.py COMMAND --help` for options.

## Tests

```bash
python -m pytest boost_library_usage_dashboard/tests/ -v
```

(from repo root; see root [README](../README.md#running-tests).)
