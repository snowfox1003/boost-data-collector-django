# Boost Library Tracker

## Overview

Tracks **Boost C++ libraries** (metadata, dependencies, GitHub linkage, releases) in the database with several **maintenance and import commands** in addition to the primary scheduled collector. Heavy use of CSV imports and backfills for library files and renames.

## Data workflow

The primary entry point is **`run_boost_github_activity_tracker`**, which ties together GitHub ingest, Markdown publishing, and optional Pinecone. Service details: [docs/service_api/boost_library_tracker.md](../docs/service_api/boost_library_tracker.md). Orchestration and Celery wiring: [docs/Workflow.md](../docs/Workflow.md), [docs/Architecture_data_flow.md](../docs/Architecture_data_flow.md).

### Where we fetch data

**GitHub** for the **boostorg/boost** super-repo and linked submodules (issues, PRs, commits, release metadata), using shared clients from `core.operations.github_ops`. Additional commands may read **local CSVs** or run tools such as **boostdep** inside a clone (`import_boost_dependencies`, file/link maintenance—see management commands below).

### How data is saved to the database

ORM models in this app store **library metadata, Boost versions, dependencies, GitHub file linkage, and activity-derived fields**. Ingest also writes/updates related rows owned by [`github_activity_tracker`](../github_activity_tracker/README.md) when the GitHub sync phase runs. Intermediate and raw artifacts land under `WORKSPACE_DIR` as configured for the pipeline. **References:** [docs/Schema.md, section 3 — Boost Library Tracker](../docs/Schema.md#3-boost-library-tracker) · [`models.py`](models.py) · [docs/service_api/boost_library_tracker.md](../docs/service_api/boost_library_tracker.md).

### How content is published to GitHub

`run_boost_github_activity_tracker` can **render issues/PRs to Markdown** and **`upload_folder_to_github`** (via `core.operations.md_ops.github_export`) into the tracker repo configured with **`BOOST_LIBRARY_TRACKER_REPO_*`** settings. Use `--skip-markdown-export` or `--skip-remote-push` to disable those phases; **`GITHUB_TOKEN_WRITE`** (or fallback token) must be available for uploads and git operations.

### How vectors sync to Pinecone

Unless `--skip-pinecone` is set, the command invokes **`run_cppa_pinecone_sync`** with the GitHub issue/PR preprocessor so vectors land in the configured Pinecone **namespace** for search/RAG. Status and failures are recorded in [`cppa_pinecone_sync`](../cppa_pinecone_sync/README.md) tables. See [docs/Pinecone_preprocess_guideline.md](../docs/Pinecone_preprocess_guideline.md).

## Common tasks

- Run the main collector: `python manage.py run_boost_github_activity_tracker` (see command `--help` and [docs/Workflow.md](../docs/Workflow.md)).
- One-off imports/backfills: see the **Management commands** section below and module docstrings.

## Main command: `run_boost_github_activity_tracker`

End-to-end Boost GitHub pipeline: sync **boostorg/boost** (+ submodules) → export issues/PRs as Markdown → push to `BOOST_LIBRARY_TRACKER_REPO_*` → Pinecone upsert (unless skipped).

| Option | Description |
| --- | --- |
| `--dry-run` | Log planned steps; no sync, export, push, or Pinecone writes. |
| `--skip-github-sync` | Skip GitHub API / `sync_github` for boostorg/boost tree. |
| `--skip-markdown-export` | Skip Markdown file generation from this run’s results. |
| `--skip-remote-push` | Skip upload to the tracker Markdown repo. |
| `--skip-pinecone` | Skip `run_cppa_pinecone_sync` for issues/PRs. |
| `--since`, `--from-date`, `--start-time` | Sync window start (`YYYY-MM-DD` or ISO datetime, UTC-normalized). |
| `--until`, `--to-date`, `--end-time` | Sync window end (same formats; deprecated alias names still accepted). |
| `--from-repo`, `--from-library` | Start ordered repo list at **`boost`** or a **submodule name** from `.gitmodules` (`--from-library` is deprecated). |

## Package

- **Django app label:** `boost_library_tracker`
- **Path (from repo root):** `boost_library_tracker/`
- **Registration:** Listed under `INSTALLED_APPS` in [`config/settings.py`](../config/settings.py) as `boost_library_tracker`.

## Management commands

| Command | Description |
| --- | --- |
| `backfill_file_renames` | Backfill previous_filename_id for renamed files in GitHubFile model. |
| `check_new_boost_release` | Exit 0 if a new Boost release exists (not in BoostVersion), else 1; for scheduler/automation. |
| `collect_boost_libraries` | Management command: collect Boost versions and library metadata. |
| `fill_boost_files` | Link unlinked repo files to the single library per repo; write missing files to CSV. |
| `import_boost_dependencies` | Import Boost dependency data by running boostdep in the boost clone; populates BoostDependency. |
| `import_boost_file_from_csv` | Link existing GitHubFile rows to BoostLibrary via BoostFile using a CSV of library_name, file_name. |
| `run_boost_github_activity_tracker` | Sync Boost GitHub activity, export issues/PRs as Markdown, push to repo, Pinecone upsert. |

Run `python manage.py <command> --help` for options.

## Tests

Typical invocation (from repo root, after [README prerequisites](../README.md#running-tests)):

```bash
python -m pytest boost_library_tracker/tests/ -v
```
