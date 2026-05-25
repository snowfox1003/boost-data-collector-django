# CPPA Pinecone Sync

## Overview

**Vector sync only.** This Django app is the shared pipeline that **embeds and upserts** documents into **Pinecone** (hybrid dense + sparse, integrated cloud embeddings). It does **not** crawl GitHub, Slack, or the web; upstream collectors populate PostgreSQL and/or the workspace, then call **`sync_to_pinecone()`** or **`run_cppa_pinecone_sync`**.

Each run targets exactly one logical source (**`--app-type`**), one **namespace**, one **preprocessor** import path, and one **Pinecone account** selected by **`--pinecone-instance`** (`public` or `private` — see [`types.PineconeInstance`](types.py)).

**Cross-app entry:** Other tracker apps import [`sync_api`](sync_api.py) only (`sync_to_pinecone`, `PineconeInstance`) — not `sync`, `ingestion`, or `services` directly.

**Docs:** [docs/service_api/cppa_pinecone_sync.md](../docs/service_api/cppa_pinecone_sync.md) · [docs/Pinecone_preprocess_guideline.md](../docs/Pinecone_preprocess_guideline.md) · [docs/Architecture_data_flow.md](../docs/Architecture_data_flow.md)

## What runs in a sync

1. **Load sync bookkeeping** from this app’s models (`PineconeSyncStatus`, `PineconeFailList`) so runs can resume and retry safely.
2. **Import and run the preprocessor** you pass in (`--preprocessor` dotted path). That callable reads **other apps’** rows and/or workspace files and returns document dicts for embedding.
3. **Chunk, embed, and upsert** into Pinecone via [`ingestion.PineconeIngestion`](ingestion.py), using the API key for the chosen **`PineconeInstance`** (`PINECONE_API_KEY` vs `PINECONE_PRIVATE_API_KEY` and related settings).
4. **Update** `PineconeSyncStatus` / `PineconeFailList` only — domain tables stay owned by the source app.

## Pinecone instance (`public` vs `private`)

| CLI | Meaning |
| --- | --- |
| `--pinecone-instance public` (default) | Use the **public** Pinecone project credentials from Django settings (`PINECONE_API_KEY`, index/host settings, embedding model names). |
| `--pinecone-instance private` | Use the **private** Pinecone project (`PINECONE_PRIVATE_API_KEY` and its index configuration). |

Pick the instance that matches where the **namespace** for this `app_type` was provisioned. Wrong instance → wrong index/credentials, not a second “mode” of ingest.

## What this app stores in PostgreSQL

Only **sync metadata** lives here — not messages, issues, or docs.

| Model | Role |
| --- | --- |
| **`PineconeSyncStatus`** | One row per `app_type`; `final_sync_at` marks last successful sync for incrementality with preprocessors. |
| **`PineconeFailList`** | Failed vector ids (and `app_type`) for retry or audit. |

**References:** [docs/Schema.md, section 9 — CPPA Pinecone Sync](../docs/Schema.md#9-cppa-pinecone-sync) · [`models.py`](models.py) · [docs/service_api/cppa_pinecone_sync.md](../docs/service_api/cppa_pinecone_sync.md).

## What this app does *not* do

- **No external “fetch” phase** — no scheduled scrape of third-party APIs inside this package.
- **No GitHub / Markdown publishing** — those belong to tracker apps and `core.operations`.
- **No writes to other apps’ domain tables** — preprocessors read them; this app only updates **`cppa_pinecone_sync_*`** tables and calls the Pinecone API.

## Common tasks

- One-off sync: `python manage.py run_cppa_pinecone_sync --help` (requires `--app-type`, `--namespace`, `--preprocessor` together).
- Add a new namespace: implement a preprocessor per [docs/Pinecone_preprocess_guideline.md](../docs/Pinecone_preprocess_guideline.md), then invoke from the owning collector or Celery task.

## Main command: `run_cppa_pinecone_sync`

Wraps **`sync_to_pinecone()`** for a single **(app_type, namespace, preprocessor, instance)** tuple.

| Option | Description |
| --- | --- |
| `--app-type` | Logical source id (string your preprocessor understands; often matches the upstream collector’s app type). |
| `--namespace` | Target Pinecone namespace for upserts. |
| `--preprocessor` | Dotted import path to the preprocess callable (e.g. `myapp.preprocessors.foo`). |
| `--pinecone-instance` | `public` (default) or `private` — which Pinecone API credentials / project to use ([`PineconeInstance`](types.py)). |

## Package

- **Django app label:** `cppa_pinecone_sync`
- **Path (from repo root):** `cppa_pinecone_sync/`
- **Registration:** Listed under `INSTALLED_APPS` in [`config/settings.py`](../config/settings.py) as `cppa_pinecone_sync`.

## Management commands

| Command | Description |
| --- | --- |
| `run_cppa_pinecone_sync` | Run one preprocessor-driven upsert into Pinecone for the given app type, namespace, and instance. |

Run `python manage.py <command> --help` for options.

## Tests

Typical invocation (from repo root, after [README prerequisites](../README.md#running-tests)):

```bash
python -m pytest cppa_pinecone_sync/tests/ -v
```
