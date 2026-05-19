# WG21 Paper Tracker

## Overview

Tracks **ISO C++ committee (WG21) mailing** paper metadata: fetch pipeline, DB updates, and optional **GitHub `repository_dispatch`** for downstream automation. Collector logic lives in [`collectors.py`](collectors.py) and the pipeline module.

## Common tasks

- Run tracker: `python manage.py run_wg21_paper_tracker --help`
- Import metadata from CSV: `python manage.py import_wg21_metadata_from_csv --help`

## Main command: `run_wg21_paper_tracker`

Runs the WG21 mailing scrape / DB pipeline and optional **`repository_dispatch`** to GitHub when enabled in settings.

| Option | Description |
| --- | --- |
| `--dry-run` | Log planned work only; no pipeline or dispatch. |
| `--from-date` | Lower bound mailing month `YYYY-MM` (inclusive backfill from that month). |
| `--to-date` | Upper bound `YYYY-MM`; with `--from-date` forms an inclusive range. |

## Package

- **Django app label:** `wg21_paper_tracker`
- **Path (from repo root):** `wg21_paper_tracker/`
- **Registration:** Listed under `INSTALLED_APPS` in [`config/settings.py`](../config/settings.py) as `wg21_paper_tracker`.

## Management commands

| Command | Description |
| --- | --- |
| `import_wg21_metadata_from_csv` | Import WG21 mailing, paper, and author metadata from CSV. |
| `run_wg21_paper_tracker` | Run WG21 paper tracker and optionally trigger GitHub repository_dispatch. |

Run `python manage.py <command> --help` for options.

## Tests

Typical invocation (from repo root, after [README prerequisites](../README.md#running-tests)):

```bash
python -m pytest wg21_paper_tracker/tests/ -v
```
