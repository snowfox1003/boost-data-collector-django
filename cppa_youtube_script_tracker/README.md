# CPPA YouTube Script Tracker

## Overview

Large surface area: ingests **YouTube / script–related** data for CPPA workflows, with a primary `run_cppa_youtube_script_tracker` command and many options (sources, dry-run, batching). Prefer reading the command module docstring and `--help` before changing defaults.

## Data workflow

The command runs in **phases**: queued metadata JSON → **YouTube Data API** video discovery → **transcript download** (VTT/text) → optional **Pinecone** upsert. Service details: [docs/service_api/cppa_youtube_script_tracker.md](../docs/service_api/cppa_youtube_script_tracker.md). See [docs/Architecture_data_flow.md](../docs/Architecture_data_flow.md).

### Where we fetch data

**YouTube Data API** for channel/video metadata within the configured time window, plus **transcript providers** for caption text. Local **queue JSON** under the workspace is processed before network phases when present.

### How data is saved to the database

Videos, transcripts, channels, and related linkage rows are persisted in this app’s models. Raw transcript files and metadata snapshots are also stored under **`WORKSPACE_DIR`** for auditing and replays. **References:** [docs/Schema.md, section 10 — CPPA YouTube Script Tracker](../docs/Schema.md#10-cppa-youtube-script-tracker) · [`models.py`](models.py) · [docs/service_api/cppa_youtube_script_tracker.md](../docs/service_api/cppa_youtube_script_tracker.md).

### How content is published to GitHub

**Not applicable** for the main collector. There is no Markdown repo publishing step in `run_cppa_youtube_script_tracker`.

### How vectors sync to Pinecone

After successful ingest, the collector can shell out to **`run_cppa_pinecone_sync`** using **`--pinecone-app-id`** and **`--pinecone-namespace`** (defaults from environment—see `--help`). Failures are surfaced in logs; detailed retry state lives in [`cppa_pinecone_sync`](../cppa_pinecone_sync/README.md) models. See [docs/Pinecone_preprocess_guideline.md](../docs/Pinecone_preprocess_guideline.md).

## Common tasks

- `python manage.py run_cppa_youtube_script_tracker --help`
- Run targeted tests: `python -m pytest cppa_youtube_script_tracker/tests/ -v` (see the **Tests** section below).

## Main command: `run_cppa_youtube_script_tracker`

Phases: (1) process queued metadata JSONs, (2) YouTube Data API video fetch for the time window, (3) transcript download—then optional Pinecone.

| Option | Description |
| --- | --- |
| `--start-time` | ISO datetime; only videos **published after** this time. Default: latest `published_at` in DB (or `YOUTUBE_DEFAULT_PUBLISHED_AFTER` if empty). |
| `--end-time` | ISO datetime upper bound; default **now**. |
| `--channel-title` | Restrict to one channel title (must match configured channel map / search). |
| `--dry-run` | Skip DB writes and API calls. |
| `--skip-transcript` | Skip phase 3 (transcripts). |
| `--pinecone-app-id` | App id passed through to `run_cppa_pinecone_sync` (default **`youtube`**). |
| `--pinecone-namespace` | Namespace for Pinecone (default from env, see command `--help`). |

## Package

- **Django app label:** `cppa_youtube_script_tracker`
- **Path (from repo root):** `cppa_youtube_script_tracker/`
- **Registration:** Listed under `INSTALLED_APPS` in [`config/settings.py`](../config/settings.py) as `cppa_youtube_script_tracker`.

## Management commands

| Command | Description |
| --- | --- |
| `run_cppa_youtube_script_tracker` | Management command: run_cppa_youtube_script_tracker |

Run `python manage.py <command> --help` for options.

## Tests

Typical invocation (from repo root, after [README prerequisites](../README.md#running-tests)):

```bash
python -m pytest cppa_youtube_script_tracker/tests/ -v
```
