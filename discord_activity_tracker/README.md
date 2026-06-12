# Discord Activity Tracker

## Overview

Ingests **Discord server activity** (messages, threads, exports) into PostgreSQL and related stores, using workspace paths and optional preprocessors. Uses **DiscordChatExporter** and shared operations documented under [docs/operations/discord_chat_exporter.md](../docs/operations/discord_chat_exporter.md).

## Data workflow

`run_discord_activity_tracker` chains **exporter fetch → PostgreSQL → Markdown on disk → optional git push → optional Pinecone**. Service API: [docs/service_api/discord_activity_tracker.md](../docs/service_api/discord_activity_tracker.md). Architecture context: [docs/Architecture_data_flow.md](../docs/Architecture_data_flow.md).

### Where we fetch data

**Discord** via **DiscordChatExporter** (configured credentials + server/channel configuration) within the `--since`/`--until` window, honoring resume semantics documented in the command help.

### How data is saved to the database

Messages, threads, and related entities are upserted into this app’s models. **Raw JSON** exports and intermediate artifacts are archived under `WORKSPACE_DIR` for replay and backfills (`backfill_discord_activity_tracker` reads the fixed import subtree). **References:** [docs/Schema.md, section 11 — Discord Activity Tracker](../docs/Schema.md#11-discord-activity-tracker-discord_activity_tracker) · [`models.py`](models.py) · [docs/service_api/discord_activity_tracker.md](../docs/service_api/discord_activity_tracker.md).

### How content is published to GitHub

Markdown is written under **`DISCORD_CONTEXT_REPO_PATH`**. When auto-commit is enabled and `--skip-remote-push` is **not** set, the collector **commits and pushes** that context repository using local git (see [`sync/export.py`](sync/export.py)). Configure credentials and remotes per your deployment docs.

### How vectors sync to Pinecone

Unless `--skip-pinecone` (or deprecated `--ignore-pinecone`) is set, the run invokes **`run_cppa_pinecone_sync`** with the Discord preprocessor so message text becomes searchable vectors in the configured namespace. See [docs/Pinecone_preprocess_guideline.md](../docs/Pinecone_preprocess_guideline.md).

## Common tasks

- Run the main tracker: `python manage.py run_discord_activity_tracker --help`.
- Historical repair: `python manage.py backfill_discord_activity_tracker --help`.
- App-specific service API: [docs/service_api/discord_activity_tracker.md](../docs/service_api/discord_activity_tracker.md).

## Main command: `run_discord_activity_tracker`

Orchestrates exporter fetch → DB upsert + raw JSON → Markdown export to `DISCORD_CONTEXT_REPO_PATH` → optional Pinecone via `run_cppa_pinecone_sync`. Requires configured Discord credentials (see `.env.example`), plus `DISCORD_SERVER_ID`; channel scope from `DISCORD_CHANNEL_IDS` unless `--channels` is set.

| Option | Description |
| --- | --- |
| `--dry-run` | Log planned steps only; no fetch, export, push, or Pinecone writes. |
| `--skip-discord-sync` | Skip DiscordChatExporter fetch, DB upserts, and raw JSON archival. |
| `--skip-markdown-export` | Skip writing Markdown from the DB to `DISCORD_CONTEXT_REPO_PATH`. |
| `--skip-remote-push` | Skip git commit/push after Markdown export (when auto-commit is enabled). |
| `--skip-pinecone` / `--ignore-pinecone` | Skip Pinecone upsert for Discord messages (`--ignore-pinecone` is a deprecated alias). |
| `--since`, `--from-date`, `--start-time` | Exporter lower bound (`--after`): `YYYY-MM-DD` or ISO-8601 UTC. If omitted, resumes from latest DB message for the guild (or today UTC only if empty). |
| `--until`, `--to-date`, `--end-time` | Exporter upper bound (`--before`); same formats. Omitted = through present. |
| `--channels` | Comma-separated channel IDs (overrides `DISCORD_CHANNEL_IDS`). |
| `--task` | **Deprecated.** `sync` \| `export` \| `all` — prefer `--skip-*` flags. |

### `backfill_discord_activity_tracker`

Imports DiscordChatExporter JSON from the fixed workspace subtree (see command `help`), deletes each file after a successful import.

| Option | Description |
| --- | --- |
| `--skip-pinecone` / `--ignore-pinecone` | Skip Pinecone after import (`--ignore-pinecone` is a deprecated alias). |
| `--dry-run` | List JSON files that would be imported without writing or deleting them. |

## Management commands

| Command | Purpose |
| --- | --- |
| `run_discord_activity_tracker` | Primary sync / collection command. |
| `backfill_discord_activity_tracker` | Backfill or repair historical activity data. |

Run `python manage.py COMMAND --help` for options.

## Tests

```bash
python -m pytest discord_activity_tracker/tests/ -v
```

(from repo root; see root [README](../README.md#running-tests).)
