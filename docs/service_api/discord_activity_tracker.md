# discord_activity_tracker.services

**Module path:** `discord_activity_tracker.services`
**Description:** Discord servers, channels, messages, and reactions. Single place for all writes to discord_activity_tracker models. Discord user profiles live in `cppa_user_tracker.DiscordProfile`.

**Type notation:** Model types refer to `discord_activity_tracker.models` unless noted. `DiscordProfile` refers to `cppa_user_tracker.models.DiscordProfile`.

---

## DiscordServer

| Function                      | Parameter types                                                    | Return type                  | Description                                                       |
| ----------------------------- | ------------------------------------------------------------------ | ---------------------------- | ----------------------------------------------------------------- |
| `get_or_create_discord_server` | `server_id: int`, `server_name: str`, `icon_url: str = ""`        | `tuple[DiscordServer, bool]` | Get or create server; update name/icon if changed.               |

---

## DiscordChannel

New fields (migration `0005`): `category_id: BigIntegerField | null`, `category_name: CharField`.

| Function                        | Parameter types                                                                                                                                          | Return type                    | Description                                                               |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------ | ------------------------------------------------------------------------- |
| `get_or_create_discord_channel` | `server: DiscordServer`, `channel_id: int`, `channel_name: str`, `channel_type: str`, `topic: str = ""`, `position: int = 0`, `category_id: int \| None = None`, `category_name: str = ""` | `tuple[DiscordChannel, bool]`  | Get or create channel; update all fields (incl. category) if changed.    |
| `update_channel_last_activity`  | `channel: DiscordChannel`, `last_activity_at: datetime`                                                                                                  | `DiscordChannel`               | Update `last_activity_at`.                                                |
| `update_channel_last_synced`    | `channel: DiscordChannel`, `timestamp: datetime \| None = None`                                                                                          | `DiscordChannel`               | Update `last_synced_at` (defaults to now).                               |

---

## DiscordMessage

New fields (migration `0005`): `message_type: CharField` (default `"Default"`), `is_pinned: BooleanField` (default `False`).

| Function                           | Parameter types                                                                                                                                                                                                                           | Return type                    | Description                    |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------ | ------------------------------ |
| `create_or_update_discord_message` | `message_id: int`, `channel: DiscordChannel`, `author: DiscordProfile`, `content: str`, `message_created_at: datetime`, `message_edited_at: datetime \| None = None`, `reply_to_message_id: int \| None = None`, `attachment_urls: list \| None = None`, `message_type: str = "Default"`, `is_pinned: bool = False` | `tuple[DiscordMessage, bool]`  | Create or update message.      |
| `mark_message_deleted`             | `message: DiscordMessage`, `deleted_at: datetime \| None = None`                                                                                                                                                                          | `DiscordMessage`               | Mark message as deleted.       |

---

## DiscordReaction

| Function                 | Parameter types                                        | Return type                     | Description              |
| ------------------------ | ------------------------------------------------------ | ------------------------------- | ------------------------ |
| `add_or_update_reaction` | `message: DiscordMessage`, `emoji: str`, `count: int`  | `tuple[DiscordReaction, bool]`  | Add or update reaction.  |

---

## Bulk operations

Message and reaction upserts use `bulk_create(update_conflicts=True)` on `DiscordMessage` and `DiscordReaction`. **`bulk_upsert_discord_users`** does not: `DiscordProfile` uses multi-table inheritance, so users are deduplicated and updated with targeted queries / `get_or_create_discord_profile` per missing row (see `services.py`).

Inputs are lists of pre-normalised message dicts (from `sync.messages._prepare_message_data` or `sync.chat_exporter.convert_exporter_message_to_dict`).

| Function                      | Parameter types                                                                                         | Return type | Description                                                                                     |
| ----------------------------- | ------------------------------------------------------------------------------------------------------- | ----------- | ----------------------------------------------------------------------------------------------- |
| `bulk_upsert_discord_users`   | `user_data_list: list[dict]`                                                                            | `dict[int, DiscordProfile]` | Upsert `DiscordProfile` rows; returns `{discord_user_id: profile}`.                             |
| `bulk_upsert_discord_messages` | `message_data_list: list[dict]`, `channel: DiscordChannel`, `user_map: dict[int, DiscordProfile]`     | `dict[int, DiscordMessage]` | Upsert `DiscordMessage` rows incl. `message_type` and `is_pinned`; returns `{message_id: msg}`. |
| `bulk_upsert_discord_reactions` | `reaction_data_list: list[dict]`, `message_map: dict[int, DiscordMessage]`                            | `None`      | Upsert `DiscordReaction` rows.                                                                  |
| `bulk_process_message_batch`  | `message_data_list: list[dict]`, `channel: DiscordChannel`                                             | `int`       | Orchestrates user upsert → message upsert → reaction upsert; returns number of messages upserted. |

---

## Query helpers

| Function              | Parameter types                                                    | Return type | Description                                         |
| --------------------- | ------------------------------------------------------------------ | ----------- | --------------------------------------------------- |
| `get_active_channels` | `server: DiscordServer`, `days: int = 30`, `channel_ids: list[int] \| None = None` | `QuerySet`  | Channels with activity in last N days, optionally filtered by `channel_ids` allowlist. |

---

## Sync package (`discord_activity_tracker.sync`)

| Module / symbol | Role |
| --------------- | ---- |
| `sync/chat_exporter.py` | Runs **DiscordChatExporter** (`exportguild`, etc.), date bounds in UTC, filters JSON paths. Used by **`run_discord_activity_tracker`**. |
| `sync/messages.py` | `_prepare_message_data`, `_process_messages_in_batches` (calls `bulk_process_message_batch`). Also exposes **discord.py** helpers (`DiscordSyncClient`, `sync_all_channels`, …) for Bot API–style sync; those entry points are **not** wired to `run_discord_activity_tracker` today (that command uses the exporter + user token only). |
| `sync/client.py` | `DiscordSyncClient` — discord.py wrapper (intents, fetch guild/channel/messages). |
| `sync/exporter_window.py` | `latest_message_created_at_for_guild` — lower bound for incremental exporter runs when `--since` is omitted. |
| `sync/utils.py` | Parsing helpers shared by exporter and message pipelines. |
| `sync/export.py` | Markdown export from DB (used downstream of sync; see command help for `DISCORD_CONTEXT_*` settings). |

---

## Ingestion commands

Two management commands handle message ingestion. Both follow the `CollectorBase` pattern with four phases: **fetch → db_sync → save_raw → pinecone_sync**.

### `run_discord_activity_tracker` — incremental / scheduled

Uses **DiscordChatExporter** CLI with the user token. Setup (download, install path, env vars): [DiscordChatExporter operations doc](../operations/discord_chat_exporter.md).

Fetches into a staging directory, persists to the database, then archives JSON under:

`{WORKSPACE_DIR}/raw/discord_activity_tracker/<server_id>/<channel_id>/`

Date bounds passed to the exporter use **UTC** (see `sync/chat_exporter.py`). When `--since` is omitted, the lower bound is the latest stored message time for this guild (and channel allowlist). If the database has no matching rows, no `--after` filter is applied (full history). When `--until` is omitted, there is no upper bound (export through the present). If `--since` and `--until` are both set but **since is after until**, the command logs a warning and treats both as unset, then recomputes bounds from the rules above.

```
python manage.py run_discord_activity_tracker [options]

Options:
  --dry-run                 No fetch, export, push, or Pinecone writes; planned steps logged at INFO
  --skip-discord-sync       Skip DiscordChatExporter, DB upserts, and raw JSON
  --skip-markdown-export    Skip writing Markdown from DB to DISCORD_CONTEXT_REPO_PATH
  --skip-remote-push        Skip git commit/push after export (see DISCORD_CONTEXT_AUTO_COMMIT)
  --skip-pinecone           Skip run_cppa_pinecone_sync
  --ignore-pinecone         Deprecated alias for --skip-pinecone
  --since, --until          ISO or YYYY-MM-DD window (UTC; aliases: --from-date, --to-date, --start-time, --end-time). Omit `--since` to continue from latest DB message; omit `--until` for no upper bound.
  --channels IDS            Comma-separated channel ID override
  --task {sync,export,all}  Deprecated: maps to the skip flags (prefer --skip-*)
```

### `backfill_discord_activity_tracker` — import JSON from workspace

Imports **existing** DiscordChatExporter JSON files from:

`{WORKSPACE_DIR}/discord_activity_tracker/Discussion - c-cpp-discussion/`

(recursively; skips macOS `._*.json` sidecars). Each file is parsed, upserted into the database, then **deleted** after a successful import so it is not processed again. Does **not** invoke DiscordChatExporter itself — export JSON elsewhere or manually, then drop it into that folder.

```
python manage.py backfill_discord_activity_tracker [options]

Options:
  --skip-pinecone          Skip Pinecone sync after import
  --ignore-pinecone        Deprecated alias for --skip-pinecone
  --dry-run                List files that would be imported; no DB writes or deletes
```

### Channel allowlist

`run_discord_activity_tracker` respects `DISCORD_CHANNEL_IDS` in `settings.py` (from the `DISCORD_CHANNEL_IDS` env var, comma-separated snowflake IDs). The `--channels` CLI argument overrides the setting for a single run.

`backfill_discord_activity_tracker` imports every JSON file under the drop folder; it does not filter by `DISCORD_CHANNEL_IDS`.

---

## Pinecone integration

`discord_activity_tracker/preprocessor.py` exposes `preprocess_discord_for_pinecone(failed_ids, final_sync_at)` which:

1. Queries `DiscordMessage` rows (incremental: `updated_at` after `final_sync_at`, plus any `failed_ids` retry; first run with no watermark indexes all non-deleted messages).
2. Groups messages into reply chains (`reply_to_message_id` linking).
3. Filters documents with fewer than `PINECONE_MIN_TEXT_LENGTH` (default 20) characters.
4. Emits `{"content": str, "metadata": {...}}` dicts with metadata keys: `doc_id`, `type`, `channel_id`, `channel_name`, `server_id`, `server_name`, `author`, `timestamp`, `is_reply_chain`, `source_ids`.

Settings:

| Setting                       | Default             | Description                              |
| ----------------------------- | ------------------- | ---------------------------------------- |
| `PINECONE_DISCORD_APP_TYPE`   | (empty skips sync) | Passed to `run_cppa_pinecone_sync` as `--app-type`. If unset/empty, Pinecone sync is skipped. |
| `PINECONE_DISCORD_NAMESPACE`  | (empty skips sync) | Pinecone namespace. If unset/empty, Pinecone sync is skipped.  |

---

## Related

- [DiscordChatExporter setup](../operations/discord_chat_exporter.md) — download, install, `.env`
- [Service API index](README.md)
- [Contributing](../Contributing.md)
- [Schema](../Schema.md)
- [Workspace](../Workspace.md) – raw archives under `{WORKSPACE_DIR}/raw/discord_activity_tracker/<server_id>/<channel_id>/`; app folder `{WORKSPACE_DIR}/discord_activity_tracker/` (CLI `script/`, backfill drop `Discussion - c-cpp-discussion/`)
