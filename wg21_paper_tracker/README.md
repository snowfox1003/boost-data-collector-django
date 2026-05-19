# WG21 Paper Tracker

## Overview

Tracks **ISO C++ committee (WG21) mailing** paper metadata: fetch pipeline, DB updates, and optional **GitHub `repository_dispatch`** for downstream automation. Collector logic lives in [`collectors.py`](collectors.py) and the pipeline module.

## Data workflow

`run_wg21_paper_tracker` scrapes or imports committee mailings into PostgreSQL, then can signal automation hosts via **GitHub’s repository_dispatch** API when configured—distinct from publishing Markdown repos. Service details: [docs/service_api/wg21_paper_tracker.md](../docs/service_api/wg21_paper_tracker.md).

### Where we fetch data

HTTP scrapes of the **WG21 papers site** ([`wg21_paper_tracker/fetcher.py`](fetcher.py)):

- **Mailing index:** `https://www.open-std.org/jtc1/sc22/wg21/docs/papers/` — lists mailings as links like `2025/#mailing2025-02`.
- **Per-year mailing pages:** `https://www.open-std.org/jtc1/sc22/wg21/docs/papers/<year>/` (e.g. `.../papers/2025/`) — each page holds anchored sections `mailingYYYY-MM` and the paper tables; paper PDFs/HTML live on the same host (resolved relative to that page).

`run_wg21_paper_tracker` limits which mailings are processed using **`--from-date` / `--to-date`** (`YYYY-MM`). **`import_wg21_metadata_from_csv`** reads **local CSV** files instead of the network (see command `--help`).

### How data is saved to the database

Papers, revisions, authors, and mailing metadata are upserted into this app’s models. Intermediate HTML or parse artifacts may land under `WORKSPACE_DIR` depending on pipeline settings. **References:** [docs/Schema.md, section 7 — WG21 Papers Tracker](../docs/Schema.md#7-wg21-papers-tracker) · [`models.py`](models.py) · [docs/service_api/wg21_paper_tracker.md](../docs/service_api/wg21_paper_tracker.md).

### How content is published to GitHub

When enabled in settings, the tracker posts a **`repository_dispatch`** event to a configured GitHub repository (for downstream workflows). It does **not** bulk-upload Markdown corpora like the Boost GitHub activity pipeline.

### How vectors sync to Pinecone

**Not applicable** in this app today. If committee text should become searchable vectors, add a preprocessor and invoke [`cppa_pinecone_sync`](../cppa_pinecone_sync/README.md) following [docs/Pinecone_preprocess_guideline.md](../docs/Pinecone_preprocess_guideline.md).

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
