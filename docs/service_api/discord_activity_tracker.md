# discord_activity_tracker.services

**Module path:** `discord_activity_tracker.services`
**Description:** Discord servers, channels, messages, and reactions. Single place for all writes to discord_activity_tracker models. Discord user profiles live in `cppa_user_tracker.DiscordProfile`.

**Type notation:** Model types refer to `discord_activity_tracker.models` unless noted. `DiscordProfile` refers to `cppa_user_tracker.models.DiscordProfile`.

---
<!-- SERVICE_API:GENERATED:START -->

## Public API (generated)

| Function | Parameters | Return type | Summary |
| --- | --- | --- | --- |
| `add_or_update_reaction` | message: DiscordMessage, emoji: str, count: int | Tuple[DiscordReaction, bool] | Upsert one reaction row per (message, emoji) with the given reaction count. |
| `bulk_process_message_batch` | message_data_list: List[Union[DiscordLivePreparedMessage, Dict[str, Any]]], channel: DiscordChannel | int | Run user upsert, message upsert, and reaction upsert inside one DB transaction. |
| `bulk_upsert_discord_messages` | message_data_list: Sequence[Union[DiscordLivePreparedMessage, Dict[str, Any]]], channel: DiscordChannel, user_map: Dict[int, DiscordProfile] | Dict[int, DiscordMessage] | Bulk upsert messages for one channel using ``bulk_create(update_conflicts=True)``. |
| `bulk_upsert_discord_reactions` | reaction_data_list: Sequence[Union[DiscordReactionPayload, Dict[str, Any]]], message_map: Dict[int, DiscordMessage] | None | Bulk upsert reactions using ``bulk_create(update_conflicts=True)``. |
| `bulk_upsert_discord_users` | user_data_list: List[Union[DiscordLiveUserPayload, Dict[str, Any]]] | Dict[int, DiscordProfile] | Upsert author profiles for a batch of messages. |
| `create_or_update_discord_message` | message_id: int, channel: DiscordChannel, author: DiscordProfile, content: str, message_created_at: datetime, message_edited_at: Optional[datetime] = None, reply_to_message_id: Optional[int] = None, attachment_urls: Optional[list] = None, message_type: str = 'Default', is_pinned: bool = False | Tuple[DiscordMessage, bool] | Create or update a single message by Discord ``message_id`` (upsert). |
| `get_active_channels` | server: DiscordServer, days: int = 30, channel_ids: Optional[List[int]] = None | QuerySet[DiscordChannel] | Same as ``queryset_channels_with_recent_messages`` with ``cutoff = now - days``. |
| `get_channel_latest_message_at` | channel: DiscordChannel | Optional[datetime] | Return the latest ``message_created_at`` among non-deleted messages in a channel. |
| `get_or_create_discord_channel` | server: DiscordServer, channel_id: int, channel_name: str, channel_type: str, topic: str = '', position: int = 0, category_id: Optional[int] = None, category_name: str = '' | Tuple[DiscordChannel, bool] | Get or create a channel row and refresh fields when the row already exists. |
| `get_or_create_discord_server` | server_id: int, server_name: str, icon_url: str = '' | Tuple[DiscordServer, bool] | Get or create a Discord guild (server) row and refresh metadata when it already exists. |
| `mark_message_deleted` | message: DiscordMessage, deleted_at: Optional[datetime] = None | DiscordMessage | Soft-delete a message: set ``is_deleted`` and ``deleted_at``. |
| `queryset_channels_with_recent_messages` | server: DiscordServer, cutoff: datetime, channel_ids: Optional[List[int]] = None | QuerySet[DiscordChannel] | Channels on ``server`` with at least one non-deleted message at or after ``cutoff``. |

<!-- SERVICE_API:GENERATED:END -->

## Service contract

- **get_or_create pattern:** `get_or_create_discord_server` and `get_or_create_discord_channel` return `tuple[Model, bool]` where the `bool` is Django's `created` flag (a new row was inserted on this call).
- **update_or_create pattern:** `create_or_update_discord_message` and `add_or_update_reaction` return `tuple[Model, bool]` with Django `update_or_create` semantics for `created`.
- **Partial updates:** On existing rows, server and channel helpers use `save(update_fields=[...])` when metadata changed; `mark_message_deleted` updates `is_deleted`, `deleted_at`, and `updated_at` via `update_fields`.
- **Bulk upsert:** `bulk_upsert_discord_messages` and `bulk_upsert_discord_reactions` use `bulk_create(..., update_conflicts=True, unique_fields=..., update_fields=...)`. **`bulk_upsert_discord_users`** uses per-row queries and `get_or_create_discord_profile` because `DiscordProfile` uses multi-table inheritance (no `bulk_create(update_conflicts=True)`).
- **Transactions:** `bulk_process_message_batch` wraps user → message → reaction upserts in a single `transaction.atomic()`; an unhandled exception rolls back all phases.
- **`bulk_process_message_batch` return value:** Returns `len(message_data_list)` when the input list is non-empty, **not** the count of rows successfully written. Individual messages may still be skipped inside `bulk_upsert_discord_messages` (see below).

---

## Raises and edge behavior

- **`discord_activity_tracker.services` does not intentionally raise `ValueError`** for invalid arguments; validate inputs at sync/staging boundaries where appropriate.
- **`bulk_upsert_discord_users`:** Each dict must include `user_id` (and keys used in the loop); malformed payloads can raise **`KeyError`**.
- **`bulk_upsert_discord_messages`:** If `user_map` has no profile for `message_data["author"]["user_id"]`, that message is **skipped** and a **warning** is logged (no exception). If every message in the batch is skipped, no bulk insert runs and `{}` is returned.
- **`bulk_upsert_discord_reactions`:** If `message_map` has no message for `discord_message_id`, that reaction is skipped **silently**. Duplicate `(message, emoji)` pairs in one batch keep the **last** entry.
- **ORM:** Functions may propagate Django database exceptions (e.g. `IntegrityError`, `OperationalError`) under concurrency or infrastructure faults.

---

## CollectorFailureCategory

`discord_activity_tracker.services` performs **database I/O only**. It does not call Discord HTTP APIs and does **not** assign [`CollectorFailureCategory`](../../core/errors.py) values.

Collectors, management commands, and sync layers classify failures with [`classify_failure`](../../core/errors.py) when handling exceptions (e.g. DiscordChatExporter subprocess failures wrapped in `CommandError`, discord.py HTTP errors, rate limits). If ORM errors are passed through `classify_failure`, mapping follows **`core/errors.py`** (for example `django.core.exceptions.ValidationError` may map to **`VALIDATION`** in typical paths).

---

## Sync package (`discord_activity_tracker.sync`)

| Module / symbol | Role |
| --------------- | ---- |
| `sync/chat_exporter.py` | Runs **DiscordChatExporter** per channel per UTC day (`export`), date bounds in UTC. Used by **`run_discord_activity_tracker`**. |
| `sync/raw_archive.py` | `merge_exporter_json` — merge daily JSON archives by message id under `raw/discord_activity_tracker/`. |
| `sync/messages.py` | `_prepare_message_data`, `_process_messages_in_batches` (calls `bulk_process_message_batch`). Also exposes **discord.py** helpers (`DiscordSyncClient`, `sync_all_channels`, …) for Bot API–style sync; those entry points are **not** wired to `run_discord_activity_tracker` today (that command uses the DiscordChatExporter CLI only). |
| `sync/client.py` | `DiscordSyncClient` — discord.py wrapper (intents, fetch guild/channel/messages). |
| `sync/exporter_window.py` | `latest_message_created_at_for_guild`, `iter_channel_export_days` — DB lower bound and UTC day windows for exporter runs. |
| `sync/utils.py` | Parsing helpers shared by exporter and message pipelines. |
| `sync/export.py` | Markdown export from DB (used downstream of sync; see command help for `DISCORD_CONTEXT_*` settings). |

---

## Ingestion commands

Two management commands handle message ingestion. Both use **`AbstractCollector`** via **`BaseCollectorCommand`**, with four phases: **fetch → db_sync → save_raw → pinecone_sync**.

### `run_discord_activity_tracker` — incremental / scheduled

Uses **DiscordChatExporter** CLI with configured exporter credentials. Setup (download, install path, env vars): [DiscordChatExporter operations doc](../operations/discord_chat_exporter.md).

Fetches into a staging directory, persists to the database, then archives JSON under:

`{WORKSPACE_DIR}/raw/discord_activity_tracker/<server_id>/<channel_id>/`

DiscordChatExporter runs **once per channel per UTC calendar day** in the resolved window. Date bounds use **UTC** (see `sync/chat_exporter.py` and `sync/exporter_window.py`). When `--since` is omitted, the lower bound is the latest stored message time for this guild (and channel allowlist). If the database has no matching rows, only **today (UTC)** is exported. When `--until` is omitted, there is no upper bound (export through the present). Raw archives are stored as `YYYY-MM-DD.json` per channel; later runs **merge** new messages into the same file by message id. If `--since` and `--until` are both set but **since is after until**, the command logs a warning and treats both as unset, then recomputes bounds from the rules above.

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
- [CONTRIBUTING](../../CONTRIBUTING.md)
- [Schema](../Schema.md)
- [Workspace](../Workspace.md) – raw archives under `{WORKSPACE_DIR}/raw/discord_activity_tracker/<server_id>/<channel_id>/`; app folder `{WORKSPACE_DIR}/discord_activity_tracker/` (CLI `script/`, backfill drop `Discussion - c-cpp-discussion/`)
