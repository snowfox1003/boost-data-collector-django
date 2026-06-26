# CPPA Slack Tracker

## Overview

Collects **Slack workspace data** for CPPA workflows: channels, messages, and related metadata, driven by the scheduled collector command. Shares patterns with other “run\_\*\_tracker” apps in this repo.

## Data workflow

`run_cppa_slack_tracker` is the batch entry point: it walks the Slack Web API for the configured **team** and persists normalized rows. Service details: [docs/service_api/cppa_slack_tracker.md](../docs/service_api/cppa_slack_tracker.md). Workspace JSON may retain exports for debugging or legacy imports. See [docs/Workspace.md](../docs/Workspace.md) and [docs/Architecture_data_flow.md](../docs/Architecture_data_flow.md).

### Where we fetch data

**Slack Web API** (users, channels, memberships, messages) using tokens from Django settings (`SLACK_BOT_TOKEN_*` / related configuration for the team). Optional **`--messages-json`** seeds the DB from previously exported JSON before live API sync.

### How data is saved to the database

Slack **teams, users, channels, memberships, and messages** are upserted into this app’s ORM models. Raw or supplemental JSON may be written under `WORKSPACE_DIR` when the collector is configured to archive payloads. **References:** [docs/Schema.md, section 6 — Slack Activity Tracker](../docs/Schema.md#6-slack-activity-tracker) · [`models.py`](models.py) · [docs/service_api/cppa_slack_tracker.md](../docs/service_api/cppa_slack_tracker.md).

### How content is published to GitHub

**Not applicable** for the scheduled collector.

### How vectors sync to Pinecone

After message sync, the command can call **`sync_to_pinecone`** from [`cppa_pinecone_sync`](../cppa_pinecone_sync/README.md) with [`preprocessor.py`](preprocessor.py) (`preprocess_slack_for_pinecone`), unless `--ignore-pinecone` is set. Namespace and app-type strings are derived from settings (for example `PINECONE_SLACK_NAMESPACE_PREFIX` plus team name). See [docs/Pinecone_preprocess_guideline.md](../docs/Pinecone_preprocess_guideline.md).

## Common tasks

- Run the tracker: `python manage.py run_cppa_slack_tracker --help`.
- Workspace layout: [docs/Workspace.md](../docs/Workspace.md); service API index: [docs/service_api/README.md](../docs/service_api/README.md).

## Main command: `run_cppa_slack_tracker`

Syncs Slack teams, users, channels, memberships, and messages. **Team ID** comes from `--team-id` or `SLACK_TEAM_ID` in settings. With no `--sync-*` flags, defaults to users + channels + messages (not channel memberships—pass `--sync-channel-users` for that).

| Option | Description |
| --- | --- |
| `--team-id` | Slack team ID; if omitted, uses `SLACK_TEAM_ID` from `.env` (**required** one of the two). |
| `--channel-id` | Optional channel scope; otherwise all channels in the team. |
| `--start-date` | Message sync start (`YYYY-MM-DD` or ISO). Default: continue from latest message in DB. |
| `--end-date` | Message sync end; default: today. |
| `--messages-json` | Path to JSON file or directory of legacy message payloads (loaded before API message sync). |
| `--sync-users` | Run user sync only (can combine with other `--sync-*`). |
| `--sync-channels` | Run channel list sync. |
| `--sync-channel-users` | Run channel membership sync. |
| `--sync-messages` | Run message sync only. |
| `--dry-run` | Log planned work; no DB/API changes. |
| `--ignore-pinecone` | Skip Pinecone upsert after message sync. |

## Management commands

| Command | Purpose |
| --- | --- |
| `run_cppa_slack_tracker` | Primary scheduled collector for this app. |

Run `python manage.py COMMAND --help` for options.

## Tests

```bash
python -m pytest cppa_slack_tracker/tests/ -v
```

(from repo root; see root [README](../README.md#running-tests).)
