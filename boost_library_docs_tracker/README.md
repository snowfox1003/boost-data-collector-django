# Boost Library Docs Tracker

## Overview

Fetches and converts **Boost library documentation** (HTML and related sources) into Markdown for storage and downstream search (Pinecone, etc.). Requires a working **`pandoc`** binary on the host (see root [README](../README.md#quick-start)).

## Data workflow

`run_boost_library_docs_tracker` crawls or unpacks documentation, normalizes it to Markdown, persists structured rows, then optionally **embeds the same content** into Pinecone. Service details: [docs/service_api/boost_library_docs_tracker.md](../docs/service_api/boost_library_docs_tracker.md).

### Where we fetch data

**Published docs (default, HTTP crawl)**
Crawl starts from paths derived from each library’s metadata and stays under:

- Base: `https://www.boost.org/doc/libs/<version_underscores>/`
  Example: Boost `1.90.0` → `https://www.boost.org/doc/libs/1_90_0/` (see `boost_library_docs_tracker/fetcher.py`: `BOOST_ORG_BASE` + `/doc/libs/...`).

**Downloaded source (`--use-local`)**
Per version, the source zip is downloaded (then extracted under `WORKSPACE_DIR`) using, in order:

1. `https://archives.boost.io/release/<version>/source/boost_<version_underscores>.zip`
2. Fallback: `https://github.com/boostorg/boost/archive/refs/tags/boost-<version>.zip`

**Which versions**
Pass **`--versions`** explicitly, or omit it to use the **latest row in the `BoostVersion` table** (PostgreSQL). This command does **not** call the GitHub API itself for version discovery; populate versions/libraries via **`boost_library_tracker`** (and related flows) first. Scope libraries with **`--library`** when needed.

### How data is saved to the database

**`BoostDocContent`**, **`BoostLibraryDocumentation`**, and related rows store URLs, content hashes, version links, and sync metadata; **converted Markdown lives on disk under `WORKSPACE_DIR`**, not in these table payloads (see the model docstrings in [`models.py`](models.py)). **Canonical schema:** [docs/Schema.md, section 10 — Boost Library Docs Tracker](../docs/Schema.md#10-boost-library-docs-tracker) (ER diagram and field notes). **Related docs:** [docs/boost_library_docs_tracker.md](../docs/boost_library_docs_tracker.md) (commands and workspace layout) and [docs/service_api/boost_library_docs_tracker.md](../docs/service_api/boost_library_docs_tracker.md) (service API for writes to these models).

### How content is published to GitHub

**Not part of this app’s pipeline.** There is no git commit or Markdown repo push from this collector.

### How vectors sync to Pinecone

After DB + workspace writes, the collector can call **`run_cppa_pinecone_sync`** with this app’s preprocessor (unless `--skip-pinecone` or a dry run). That upserts into the namespace configured for Boost docs search; see [docs/Pinecone_preprocess_guideline.md](../docs/Pinecone_preprocess_guideline.md).

## Common tasks

- Run the tracker: `python manage.py run_boost_library_docs_tracker --help`.
- Service-layer overview: [docs/service_api/boost_library_docs_tracker.md](../docs/service_api/boost_library_docs_tracker.md).
- Confirm `pandoc` is on `PATH` before debugging conversion failures.

## Main command: `run_boost_library_docs_tracker`

Scrapes Boost library docs for one or more versions, writes workspace + `BoostDocContent` / `BoostLibraryDocumentation` rows, then upserts Pinecone (unless skipped).

| Option | Description |
| --- | --- |
| `--versions` | Zero or more Boost versions (e.g. `1.86.0 1.87.0`). **Omitted** → latest version from the **`BoostVersion`** table (run `boost_library_tracker` first if empty). |
| `--library` | Limit scrape to one library key (e.g. `algorithm`). Default: all libraries for each version. |
| `--dry-run` | Parse/fetch without writing DB, workspace, or Pinecone. |
| `--skip-pinecone` | Write DB + workspace but skip Pinecone upsert. |
| `--max-pages` | Per-library BFS page cap when crawling HTTP (default **10**). |
| `--use-local` | Download Boost source zip and walk local HTML instead of HTTP crawl. |
| `--cleanup-extract` | With `--use-local`, delete extracted tree + downloaded zip after each version’s libraries finish. |

## Management commands

| Command | Purpose |
| --- | --- |
| `run_boost_library_docs_tracker` | Primary doc fetch / conversion pipeline. |

Run `python manage.py COMMAND --help` for options.

## Tests

```bash
python -m pytest boost_library_docs_tracker/tests/ -v
```

(from repo root; see root [README](../README.md#running-tests).)
