"""Django management command ``backfill_discord_activity_tracker``.

Imports **pre-exported** DiscordChatExporter JSON from the workspace drop folder
(``workspace/discord_activity_tracker/Discussion - c-cpp-discussion/``,
recursively), validates envelope and normalized messages, upserts into the database
via the service layer, then **deletes** each file after a successful import so it is
not processed again.

This command does **not** invoke DiscordChatExporter; place JSON exports in the drop
folder manually or from another host.

Optional arguments: ``--dry-run`` (list files only), ``--skip-pinecone`` /
``--ignore-pinecone`` (skip ``task_discord_pinecone_sync`` after import). See
``Command.add_arguments`` and ``docs/service_api/discord_activity_tracker.md``.

Side effects: DB writes to ``DiscordServer``, ``DiscordChannel``, ``DiscordMessage``,
``DiscordReaction``, and ``DiscordProfile`` (via services); filesystem deletes on
success; Pinecone sync when enabled.

Raises:
    Per-file parse/validation failures are caught inside ``DiscordBackfillCollector.collect``
    (logged and reported on stdout); they do not abort the whole command. Uncaught
    exceptions from ``sync_pinecone`` or the base command layer may still propagate.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from asgiref.sync import sync_to_async

from core.collectors import AbstractCollector, BaseCollectorCommand
from discord_activity_tracker.pinecone_runner import task_discord_pinecone_sync
from discord_activity_tracker.services import (
    get_or_create_discord_channel,
    get_or_create_discord_server,
)
from discord_activity_tracker.staging_schema import (
    validate_envelope,
    validate_normalized_message,
)
from discord_activity_tracker.sync.chat_exporter import (
    convert_exporter_message_to_dict,
    filter_discord_export_json_paths,
    parse_exported_json,
    _safe_int,
)
from discord_activity_tracker.sync.messages import _process_messages_in_batches
from discord_activity_tracker.workspace import get_cpp_discussion_import_dir

logger = logging.getLogger(__name__)


def _json_display_path(import_dir: Path, json_path: Path) -> str:
    """Short path for logs (relative to import root when possible)."""
    try:
        return str(json_path.relative_to(import_dir))
    except ValueError:
        return json_path.name


class DiscordBackfillCollector(AbstractCollector):
    """Backfill collector: scan drop folder, import each JSON, delete on success.

    ``collect()`` lists JSON under ``get_cpp_discussion_import_dir()``, optionally
    dry-run prints paths, else for each file parses, validates staging schema,
    upserts messages in batches, unlinks the file on success, or logs failure and
    keeps the file.

    ``sync_pinecone()`` runs after a successful collector run (unless dry-run or
    ``skip_pinecone``).

    Side effects: Same as module docstring (DB, deletes, optional Pinecone).
    """

    def __init__(self, *, stdout, style, **opts: Any) -> None:
        self.stdout = stdout
        self.style = style
        self.dry_run: bool = opts["dry_run"]
        self.skip_pinecone: bool = bool(opts.get("skip_pinecone"))

    @property
    def name(self) -> str:
        return "discord_activity_tracker_backfill"

    def validate_config(self) -> None:
        return None

    def collect(self) -> None:
        import_dir = get_cpp_discussion_import_dir()
        json_files = sorted(
            filter_discord_export_json_paths(import_dir.rglob("*.json"))
        )

        self.stdout.write("=== Discord JSON import (c-cpp-discussion) ===")
        self.stdout.write(f"  Folder: {import_dir}")
        self.stdout.write(f"  Files:  {len(json_files)}")

        if self.dry_run:
            for p in json_files:
                self.stdout.write(
                    f"    (dry-run) would import {_json_display_path(import_dir, p)}"
                )
            self.stdout.write(self.style.WARNING("DRY RUN — no writes or deletes"))
            return

        processed_total = 0
        for i, json_path in enumerate(json_files, 1):
            try:
                data = parse_exported_json(json_path)
                rel = _json_display_path(import_dir, json_path)
                envelope = validate_envelope(data, source=rel)
                guild_info = envelope.guild.model_dump(by_alias=True)
                channel_info = envelope.channel.model_dump(by_alias=True)
                messages = envelope.messages

                ch_name = channel_info.get("name", "?")
                self.stdout.write(
                    f"  [{i}/{len(json_files)}] {rel} — #{ch_name}: {len(messages)} messages"
                )
                count = asyncio.run(
                    self._persist_channel(guild_info, channel_info, messages)
                )
                processed_total += count
                json_path.unlink(missing_ok=True)
                self.stdout.write(
                    self.style.SUCCESS(f"    Imported {count}; removed {rel}")
                )
            except Exception as exc:
                rel = _json_display_path(import_dir, json_path)
                logger.error("Failed to process %s: %s", rel, exc)
                self.stdout.write(self.style.ERROR(f"    Failed {rel}: {exc}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"Import complete: {processed_total} messages from "
                f"{len(json_files)} file(s)"
            )
        )

    async def _persist_channel(
        self,
        guild_info: dict,
        channel_info: dict,
        messages: list,
    ) -> int:
        server, _ = await sync_to_async(get_or_create_discord_server)(
            server_id=_safe_int(guild_info.get("id", 0)),
            server_name=guild_info.get("name", ""),
            icon_url=guild_info.get("iconUrl", ""),
        )

        raw_cat_id = channel_info.get("categoryId")
        category_id = _safe_int(raw_cat_id) if raw_cat_id else None

        channel, _ = await sync_to_async(get_or_create_discord_channel)(
            server=server,
            channel_id=_safe_int(channel_info.get("id", 0)),
            channel_name=channel_info.get("name", ""),
            channel_type=channel_info.get("type", "GuildTextChat"),
            topic=channel_info.get("topic") or "",
            position=0,
            category_id=category_id,
            category_name=channel_info.get("category") or "",
        )

        srv_id = _safe_int(guild_info.get("id", 0))
        ch_id = _safe_int(channel_info.get("id", 0))
        converted = [
            convert_exporter_message_to_dict(m, server_id=srv_id, channel_id=ch_id)
            for m in messages
        ]
        for idx, cmsg in enumerate(converted):
            validate_normalized_message(cmsg, source=f"message[{idx}]")
        count = await _process_messages_in_batches(channel, converted)
        return count

    def sync_pinecone(self) -> None:
        if self.dry_run or self.skip_pinecone:
            return
        task_discord_pinecone_sync(dry_run=False)


class Command(BaseCollectorCommand):
    """``manage.py backfill_discord_activity_tracker`` — import JSON from the drop folder.

    Uses ``DiscordBackfillCollector``. Required layout: JSON files under
    ``{WORKSPACE_DIR}/discord_activity_tracker/Discussion - c-cpp-discussion/``.

    Optional arguments: ``--dry-run``, ``--skip-pinecone`` / ``--ignore-pinecone``.

    Examples:
        ``python manage.py backfill_discord_activity_tracker``

        ``python manage.py backfill_discord_activity_tracker --dry-run``

        ``python manage.py backfill_discord_activity_tracker --skip-pinecone``

    Raises:
        Per-file errors are swallowed in the collector loop; see class docstring.
        Base command / Pinecone task may raise if misconfigured.

    See Also:
        ``docs/service_api/discord_activity_tracker.md``
    """

    help = (
        "Import DiscordChatExporter JSON from "
        "workspace/discord_activity_tracker/Discussion - c-cpp-discussion/ "
        "(recursively) into the database; delete each file after successful import."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-pinecone",
            action="store_true",
            dest="skip_pinecone",
            help="Skip Pinecone sync after import",
        )
        parser.add_argument(
            "--ignore-pinecone",
            action="store_true",
            dest="skip_pinecone",
            help="Deprecated alias for --skip-pinecone.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List JSON files that would be imported without writing or deleting",
        )

    def get_collector(self, **options: Any) -> AbstractCollector:
        opts = dict(options)
        if opts.get("skip_pinecone") is None:
            opts["skip_pinecone"] = False
        return DiscordBackfillCollector(
            stdout=self.stdout,
            style=self.style,
            dry_run=opts["dry_run"],
            skip_pinecone=opts["skip_pinecone"],
        )
