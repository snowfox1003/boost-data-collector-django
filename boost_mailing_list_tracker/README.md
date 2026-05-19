# Boost Mailing List Tracker

## Overview

Tracks **Boost mailing list** activity (messages, threads, archives) into the database for dashboards and search. Runs as a standard collector app behind Celery / `run_scheduled_collectors`.

## Data workflow

The collector alternates between **workspace JSON** (staging) and **PostgreSQL** as it ingests new mail, then optionally pushes vectors for search. Service details: [docs/service_api/boost_mailing_list_tracker.md](../docs/service_api/boost_mailing_list_tracker.md). Scheduling: [docs/Workflow.md](../docs/Workflow.md), [`config/boost_collector_schedule.yaml`](../config/boost_collector_schedule.yaml).

### Where we fetch data

**Mailing list HTTP/API endpoints** configured for Boost lists (see command `--help` and service modules). Existing JSON batches under `WORKSPACE_DIR` are **processed first** (persist → delete) before new fetches run.

### How data is saved to the database

Messages and thread metadata are upserted into this app’s models. Fresh payloads are written as **JSON under the workspace** and then ingested into the ORM in the same run when not in `--dry-run`. **References:** [docs/Schema.md, section 5 — Boost Mailing List Tracker](../docs/Schema.md#5-boost-mailing-list-tracker) · [`models.py`](models.py) · [docs/service_api/boost_mailing_list_tracker.md](../docs/service_api/boost_mailing_list_tracker.md).

### How content is published to GitHub

**Not applicable.** Archives stay in PostgreSQL, workspace files, and (optionally) Pinecone—there is no Markdown repo push in this collector.

### How vectors sync to Pinecone

By default the command invokes **`run_cppa_pinecone_sync`** with [`preprocess_mailing_list_for_pinecone`](preprocessor.py) (see `preprocessor.py`), using **`--pinecone-app-type`** / **`--pinecone-namespace`** or the `BOOST_MAILING_LIST_PINECONE_*` settings. See [docs/Pinecone_preprocess_guideline.md](../docs/Pinecone_preprocess_guideline.md).

## Common tasks

- Run the tracker: `python manage.py run_boost_mailing_list_tracker --help`.
- Scheduling: [docs/Workflow.md](../docs/Workflow.md) and [`config/boost_collector_schedule.yaml`](../config/boost_collector_schedule.yaml).

## Main command: `run_boost_mailing_list_tracker`

Processes existing workspace JSONs (persist → delete), then fetches new mail from the API (write JSON → persist → remove). Optional Pinecone step uses `run_cppa_pinecone_sync` with the configured app type/namespace.

| Option | Description |
| --- | --- |
| `--start-date` | Fetch lower bound (ISO date, e.g. `2025-09-01`). Default: no lower bound (fetch all). |
| `--end-date` | Fetch upper bound (ISO). Default: no upper bound. |
| `--dry-run` | Fetch and report counts only; no DB or workspace writes. |
| `--pinecone-app-type` | Passed to `run_cppa_pinecone_sync`; default from `BOOST_MAILING_LIST_PINECONE_APP_TYPE`. |
| `--pinecone-namespace` | Pinecone namespace; default from `BOOST_MAILING_LIST_PINECONE_NAMESPACE`. |

## Management commands

| Command | Purpose |
| --- | --- |
| `run_boost_mailing_list_tracker` | Primary scheduled collector for mailing list ingestion. |

Run `python manage.py COMMAND --help` for options.

## Tests

```bash
python -m pytest boost_mailing_list_tracker/tests/ -v
```

(from repo root; see root [README](../README.md#running-tests).)
