# Boost Library Tracker

## Overview

Tracks **Boost C++ libraries** (metadata, dependencies, GitHub linkage, releases) in the database with several **maintenance and import commands** in addition to the primary scheduled collector. Heavy use of CSV imports and backfills for library files and renames.

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

## Title

**Boost Library Tracker**

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
