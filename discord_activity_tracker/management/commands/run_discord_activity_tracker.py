"""Django management command ``run_discord_activity_tracker``.

Orchestrates the scheduled Discord ingest pipeline: workspace prep, optional
DiscordChatExporter fetch with DB upsert and raw JSON archival, Markdown export to
``DISCORD_CONTEXT_REPO_PATH``, and optional Pinecone sync via ``run_cppa_pinecone_sync``.

Phases (see ``DiscordActivityCollector`` and task helpers in this module):

    1. **Workspace** — Ensure raw/staging dirs under ``WORKSPACE_DIR`` (see
       ``discord_activity_tracker.workspace``).
    2. **Sync** — Run DiscordChatExporter (unless ``--skip-discord-sync``), parse JSON,
       validate staging schema, upsert via ``discord_activity_tracker.services``,
       move exports under
       ``{WORKSPACE_DIR}/raw/discord_activity_tracker/<server_id>/<channel_id>/``.
    3. **Markdown** — Export DB rows to the context repo (unless ``--skip-markdown-export``);
       optional git push when ``DISCORD_CONTEXT_AUTO_COMMIT`` is true and
       ``--skip-remote-push`` is not set.
    4. **Pinecone** — ``task_discord_pinecone_sync`` when ``PINECONE_DISCORD_*`` are set
       and ``--skip-pinecone`` is not used.

Required settings for a full sync: ``DISCORD_USER_TOKEN``, ``DISCORD_SERVER_ID``.
Channel scope uses ``DISCORD_CHANNEL_IDS`` unless overridden by ``--channels``.

CLI flags are documented on ``Command.add_argument`` ``help=`` strings and in
``docs/service_api/discord_activity_tracker.md``.

Raises:
    django.core.management.base.CommandError: Missing token/guild, invalid
    ``--since``/``--until`` parse, or DiscordChatExporter failure (wrapped from
    ``DiscordChatExporterError``). Other exceptions from the collector may propagate
    after logging from ``_handle_core``.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.management.base import CommandError

from core.collectors import AbstractCollector, BaseCollectorCommand
from core.protocols import IncrementalState, TrackerResult
from discord_activity_tracker.protocol_impl import (
    DiscordCollectionTrackerResult,
    DiscordIncrementalState,
)
from core.utils.datetime_parsing import parse_iso_datetime
from discord_activity_tracker.models import DiscordServer
from discord_activity_tracker.pinecone_runner import task_discord_pinecone_sync
from discord_activity_tracker.services import (
    get_or_create_discord_channel,
    get_or_create_discord_server,
)
from discord_activity_tracker.staging_schema import (
    StagingValidationError,
    validate_envelope,
    validate_normalized_message,
)
from discord_activity_tracker.sync.exporter_window import (
    latest_message_created_at_for_guild,
)
from discord_activity_tracker.sync.chat_exporter import (
    DiscordChatExporterError,
    _safe_int,
    convert_exporter_message_to_dict,
    export_guild_to_json,
    filter_discord_export_json_paths,
    parse_exported_json,
)
from discord_activity_tracker.sync.messages import _process_messages_in_batches
from discord_activity_tracker.workspace import (
    clear_exporter_staging_dir,
    get_channel_raw_dir,
    get_exporter_staging_dir,
    get_raw_dir,
)

logger = logging.getLogger(__name__)


def _parse_channel_ids(raw: str) -> list[int]:
    """Parse comma-separated channel ID strings to a list of ints."""
    return [int(c.strip()) for c in raw.split(",") if c.strip().isdigit()]


def _naive_utc_to_aware_utc(dt: datetime) -> datetime:
    """``parse_iso_datetime`` returns naive UTC; attach UTC tzinfo for exporter bounds."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _resolve_exporter_date_bounds(
    options: dict,
    *,
    guild_snowflake: int,
    channel_ids: list[int],
) -> tuple[datetime | None, datetime | None]:
    """Compute ``after_date`` / ``before_date`` in UTC for DiscordChatExporter.

    - With ``--since``: lower bound is that timestamp.
    - Without ``--since``: lower bound is the latest stored ``message_created_at`` for this
      guild (scoped to the channel allowlist when set), or ``None`` if the DB has no rows
      (full-history export / no ``--after`` filter).
    - With ``--until``: upper bound is that timestamp.
    - Without ``--until``: upper bound is ``None`` (export through the present; no ``--before``).
    """
    since_s = (options.get("since") or "").strip() or None
    until_s = (options.get("until") or "").strip() or None
    try:
        since = parse_iso_datetime(since_s)
        until = parse_iso_datetime(until_s)
    except ValueError as e:
        raise CommandError(str(e)) from e

    if since and until and since > until:
        logger.warning(
            "invalid date range: since (%s) is after until (%s); falling back to defaults",
            since.isoformat(),
            until.isoformat(),
        )
        since, until = None, None

    scope = channel_ids if channel_ids else None

    if since is not None:
        after_date = _naive_utc_to_aware_utc(since)
    else:
        latest_row = latest_message_created_at_for_guild(
            guild_snowflake,
            channel_ids=scope,
        )
        after_date = (
            latest_row.astimezone(timezone.utc) if latest_row is not None else None
        )
        if after_date is not None:
            logger.debug(
                "exporter lower bound from DB (--since omitted): %s",
                after_date.isoformat(),
            )
        else:
            logger.debug(
                "exporter lower bound: none (--since omitted, empty DB for guild scope)",
            )

    if until is not None:
        before_date = _naive_utc_to_aware_utc(until)
    else:
        before_date = None

    return after_date, before_date


def task_preprocess_workspace(*, dry_run: bool) -> None:
    """Ensure ``WORKSPACE_DIR/raw/discord_activity_tracker`` and staging dirs exist."""
    # get_exporter_staging_dir() calls get_raw_dir(); both trees are mkdir'd here.
    get_exporter_staging_dir()
    if dry_run:
        logger.info(
            "dry-run would ensure raw workspace under %s",
            get_raw_dir(),
        )


def task_discord_sync(
    *,
    dry_run: bool,
    skip_discord_sync: bool,
    user_token: str,
    guild_id: int,
    channel_ids: list[int],
    after_date: datetime | None,
    before_date: datetime | None,
    collector: "DiscordActivityCollector",
) -> int:
    """DiscordChatExporter → parse → db_sync → archive JSON per channel."""
    if skip_discord_sync:
        logger.info("skipping Discord fetch / DB / raw (--skip-discord-sync)")
        return 0

    if dry_run:
        logger.info(
            "dry-run would run DiscordChatExporter and persist messages + raw JSON"
        )
        return 0

    raw_root = get_raw_dir()
    staging = get_exporter_staging_dir()
    clear_exporter_staging_dir()

    collector.stdout.write("=== Discord sync (fetch → db_sync → save_raw) ===")
    if after_date:
        collector.stdout.write(
            f"Incremental: fetching messages after {after_date.isoformat()} UTC"
        )
    else:
        collector.stdout.write("Full mode: fetching all messages (no --after filter)")
    if before_date:
        collector.stdout.write(
            f"Upper bound: messages before {before_date.isoformat()} UTC"
        )

    try:
        json_files = export_guild_to_json(
            user_token=user_token,
            guild_id=guild_id,
            output_dir=staging,
            after_date=after_date,
            before_date=before_date,
            channel_ids=channel_ids or None,
        )
    except DiscordChatExporterError as exc:
        raise CommandError(f"DiscordChatExporter failed: {exc}") from exc

    json_files = filter_discord_export_json_paths(json_files)

    collector.stdout.write(f"Exported {len(json_files)} channel file(s)")

    processed_total = 0
    for i, json_path in enumerate(json_files, 1):
        try:
            data = parse_exported_json(json_path)
            envelope = validate_envelope(data, source=json_path.name)
            guild_info = envelope.guild.model_dump(by_alias=True)
            channel_info = envelope.channel.model_dump(by_alias=True)
            messages = envelope.messages

            ch_name = channel_info.get("name", "?")
            ch_id = _safe_int(channel_info.get("id", 0))
            srv_id = _safe_int(guild_info.get("id", 0))

            if channel_ids and ch_id not in channel_ids:
                logger.debug("Skipping channel %s (not in allowlist)", ch_id)
                json_path.unlink(missing_ok=True)
                continue

            collector.stdout.write(
                f"  [{i}/{len(json_files)}] #{ch_name}: {len(messages)} messages"
            )
            count = asyncio.run(
                collector._persist_channel(guild_info, channel_info, messages)
            )
            processed_total += count

            channel_raw_dir = get_channel_raw_dir(srv_id, ch_id)
            date_tag = after_date.strftime("%Y-%m-%d") if after_date else "full"
            dest = channel_raw_dir / f"{date_tag}.json"
            json_path.rename(dest)

        except StagingValidationError as exc:
            logger.error(
                "Staging validation failed for %s (file left in staging): %s",
                json_path.name,
                exc,
            )
            continue
        except ValueError as exc:
            logger.error("Failed to process %s: %s", json_path.name, exc)
            json_path.unlink(missing_ok=True)
            continue
        except Exception as exc:
            logger.error("Failed to process %s: %s", json_path.name, exc)
            json_path.unlink(missing_ok=True)
            continue

    collector.stdout.write(
        collector.style.SUCCESS(
            f"Synced {processed_total} messages across all channels"
        )
    )
    logger.debug("raw archive root: %s", raw_root)
    return processed_total


def task_markdown_export_and_push(
    *,
    dry_run: bool,
    skip_markdown_export: bool,
    skip_remote_push: bool,
    guild_id: int,
    collector: "DiscordActivityCollector",
) -> None:
    """Export Markdown to DISCORD_CONTEXT_REPO_PATH; optional git commit/push."""
    if skip_markdown_export:
        logger.info("skipping Markdown export (--skip-markdown-export)")
        return

    from discord_activity_tracker.sync.export import export_and_push

    context_repo_path = getattr(settings, "DISCORD_CONTEXT_REPO_PATH", None)
    if not context_repo_path:
        collector.stdout.write(
            collector.style.WARNING(
                "DISCORD_CONTEXT_REPO_PATH not set; skipping export"
            )
        )
        return

    if dry_run:
        collector.stdout.write(
            "dry-run would export Markdown to " + str(context_repo_path)
        )
        return

    try:
        server = DiscordServer.objects.get(server_id=guild_id)
    except DiscordServer.DoesNotExist:
        collector.stdout.write(
            collector.style.WARNING("Server not in DB — run sync first")
        )
        return

    auto_commit = bool(
        (not skip_remote_push)
        and getattr(settings, "DISCORD_CONTEXT_AUTO_COMMIT", False)
    )
    if skip_remote_push:
        logger.info(
            "skipping remote git push (--skip-remote-push); "
            "files still written unless export fails"
        )

    success = export_and_push(
        context_repo_path=Path(context_repo_path),
        server=server,
        auto_commit=auto_commit,
    )
    if success:
        collector.stdout.write(
            collector.style.SUCCESS(f"Exported to {context_repo_path}")
        )
    else:
        collector.stdout.write(collector.style.WARNING("No markdown files exported"))


class DiscordActivityCollector(AbstractCollector):
    """Collector implementation for ``run_discord_activity_tracker``.

    Holds stdout/style, resolved ``channel_ids`` (from ``--channels`` or
    ``settings.DISCORD_CHANNEL_IDS``), and delegates to ``Command._handle_core``.

    ``collect()`` drives fetch → Markdown → Pinecone according to options.
    ``sync_pinecone()`` runs ``task_discord_pinecone_sync`` when not dry-run and not
    skipping Pinecone.

    Side effects: Same as the management command (DB, filesystem, subprocess calls
    to DiscordChatExporter and Pinecone tooling via configured runners).
    """

    def __init__(self, cmd: "Command", options: dict) -> None:
        self.cmd = cmd
        self.options = options
        self.stdout = cmd.stdout
        self.style = cmd.style

        raw_channels = (options.get("channels") or "").strip()
        if raw_channels:
            self.channel_ids: list[int] = _parse_channel_ids(raw_channels)
        else:
            self.channel_ids = list(getattr(settings, "DISCORD_CHANNEL_IDS", []))

    @property
    def name(self) -> str:
        return "discord_activity_tracker"

    def validate_config(self) -> None:
        return None

    def load_incremental_state(self) -> IncrementalState | None:
        guild_id: int | None = getattr(settings, "DISCORD_SERVER_ID", None)
        if not guild_id:
            return None
        after_date, _before = _resolve_exporter_date_bounds(
            self.options,
            guild_snowflake=guild_id,
            channel_ids=self.channel_ids,
        )
        return DiscordIncrementalState.from_after_date(after=after_date)

    def collect(self) -> TrackerResult:
        return self.cmd._handle_core(self.options, collector=self)

    def sync_pinecone(self) -> None:
        if self.options.get("dry_run") or self.options.get("skip_pinecone"):
            return
        task_discord_pinecone_sync(dry_run=False)

    async def _persist_channel(
        self,
        guild_info: dict,
        channel_info: dict,
        messages: list,
    ) -> int:
        """Persist one channel's messages to DB."""
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


class Command(BaseCollectorCommand):
    """``manage.py run_discord_activity_tracker`` — incremental Discord ingest and exports.

    Wraps ``DiscordActivityCollector`` with ``BaseCollectorCommand`` (dry-run, logging,
    collector phases). See module docstring for phases and required settings.

    Optional arguments (full text on each ``add_argument``):

        ``--dry-run``, ``--skip-discord-sync``, ``--skip-markdown-export``,
        ``--skip-remote-push``, ``--skip-pinecone`` / ``--ignore-pinecone``,
        ``--since`` / ``--until`` (and aliases), ``--channels``, ``--task`` (deprecated).

    Examples:
        ``python manage.py run_discord_activity_tracker`` — full pipeline with
        settings-based channel allowlist.

        ``python manage.py run_discord_activity_tracker --dry-run`` — log planned
        steps only.

        ``python manage.py run_discord_activity_tracker --channels 123,456 --skip-pinecone`` —
        restrict channels and skip Pinecone.

    Raises:
        CommandError: If ``DISCORD_USER_TOKEN`` or ``DISCORD_SERVER_ID`` is unset, or
        date options fail to parse, or DiscordChatExporter fails (see ``task_discord_sync``).

    See Also:
        ``docs/service_api/discord_activity_tracker.md``
        ``docs/operations/discord_chat_exporter.md``
    """

    help = (
        "Discord activity tracker: (1) fetch via DiscordChatExporter + DB + raw archive; "
        "(2) export Markdown to DISCORD_CONTEXT_REPO_PATH; "
        "(3) Pinecone upsert (PINECONE_DISCORD_* settings). "
        "Use --skip-* to skip steps; default runs all."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="No fetch, export, push, or Pinecone writes; planned steps logged at INFO.",
        )
        parser.add_argument(
            "--skip-discord-sync",
            action="store_true",
            help="Skip DiscordChatExporter fetch, DB upserts, and raw JSON archival.",
        )
        parser.add_argument(
            "--skip-markdown-export",
            action="store_true",
            help="Skip writing Markdown from the DB to DISCORD_CONTEXT_REPO_PATH.",
        )
        parser.add_argument(
            "--skip-remote-push",
            action="store_true",
            help="Skip git commit/push after Markdown export (requires DISCORD_CONTEXT_AUTO_COMMIT).",
        )
        parser.add_argument(
            "--skip-pinecone",
            action="store_true",
            dest="skip_pinecone",
            help="Skip run_cppa_pinecone_sync for Discord messages.",
        )
        parser.add_argument(
            "--ignore-pinecone",
            action="store_true",
            dest="skip_pinecone",
            help="Deprecated alias for --skip-pinecone.",
        )
        parser.add_argument(
            "--since",
            "--from-date",
            "--start-time",
            type=str,
            default=None,
            dest="since",
            help="Exporter lower bound (--after): YYYY-MM-DD or ISO-8601 (UTC). "
            "If omitted, uses the latest message time already in the DB for this guild "
            "(and channel allowlist), or full history when the DB has no rows.",
        )
        parser.add_argument(
            "--until",
            "--to-date",
            "--end-time",
            type=str,
            default=None,
            dest="until",
            help="Exporter upper bound (--before): same formats as --since; "
            "default when omitted: no upper bound (through present). "
            "--to-date is deprecated; --end-time is an alias for --until.",
        )
        parser.add_argument(
            "--channels",
            type=str,
            default="",
            help="Comma-separated channel IDs (overrides DISCORD_CHANNEL_IDS setting).",
        )
        parser.add_argument(
            "--task",
            choices=["sync", "export", "all"],
            default=None,
            help="Deprecated: prefer --skip-*. sync=fetch only; export=markdown only; all=all phases.",
        )

    def get_collector(self, **options: Any) -> AbstractCollector:
        opts = dict(options)
        if opts.get("skip_pinecone") is None:
            opts["skip_pinecone"] = False
        return DiscordActivityCollector(cmd=self, options=opts)

    def _handle_core(
        self, options: dict, collector: DiscordActivityCollector
    ) -> DiscordCollectionTrackerResult:
        dry_run = options["dry_run"]
        skip_discord_sync = options["skip_discord_sync"]
        skip_markdown_export = options["skip_markdown_export"]
        skip_remote_push = options["skip_remote_push"]
        skip_pinecone = options.get("skip_pinecone") or False

        task = options.get("task")
        if task == "sync":
            skip_markdown_export = True
            skip_remote_push = True
        elif task == "export":
            skip_discord_sync = True
            skip_pinecone = True
        elif task == "all":
            pass

        collector.options.update(
            {
                "skip_discord_sync": skip_discord_sync,
                "skip_markdown_export": skip_markdown_export,
                "skip_remote_push": skip_remote_push,
                "skip_pinecone": skip_pinecone,
            }
        )

        user_token = (getattr(settings, "DISCORD_USER_TOKEN", "") or "").strip()
        guild_id: int | None = getattr(settings, "DISCORD_SERVER_ID", None)

        if not user_token:
            raise CommandError("DISCORD_USER_TOKEN not configured.")
        if not guild_id:
            raise CommandError("DISCORD_SERVER_ID not configured.")

        try:
            after_date, before_date = _resolve_exporter_date_bounds(
                options,
                guild_snowflake=guild_id,
                channel_ids=collector.channel_ids,
            )
        except CommandError:
            raise

        logger.debug(
            "starting (dry_run=%s, skip_discord_sync=%s, skip_md=%s, skip_push=%s, skip_pinecone=%s)",
            dry_run,
            skip_discord_sync,
            skip_markdown_export,
            skip_remote_push,
            skip_pinecone,
        )

        try:
            if dry_run:
                task_preprocess_workspace(dry_run=True)
                if not skip_discord_sync:
                    logger.info("dry-run would run DiscordChatExporter + DB + raw JSON")
                else:
                    logger.info("dry-run skipping Discord sync (--skip-discord-sync)")
                if not skip_markdown_export:
                    logger.info("dry-run would export Markdown from DB")
                if not skip_remote_push:
                    logger.info(
                        "dry-run would push Markdown if DISCORD_CONTEXT_AUTO_COMMIT is enabled"
                    )
                if not skip_pinecone:
                    logger.info(
                        "dry-run would run Pinecone upsert for Discord messages"
                    )
                collector.stdout.write(collector.style.WARNING("DRY RUN — no writes"))
                collector.stdout.write(f"  Guild ID: {guild_id}")
                collector.stdout.write(
                    f"  Channel allowlist: {collector.channel_ids or 'all channels'}"
                )
                if after_date:
                    collector.stdout.write(
                        f"  Lower bound (--after): {after_date.isoformat()} UTC"
                    )
                else:
                    collector.stdout.write(
                        "  Lower bound (--after): none (full history; empty DB or no since)"
                    )
                if before_date:
                    collector.stdout.write(
                        f"  Upper bound (--before): {before_date.isoformat()} UTC"
                    )
                else:
                    collector.stdout.write(
                        "  Upper bound (--before): none (through present)"
                    )
                logger.info("finished successfully (dry-run)")
                return DiscordCollectionTrackerResult(
                    success=True, counts={"dry_run": 1}
                )

            messages_synced = task_discord_sync(
                dry_run=False,
                skip_discord_sync=skip_discord_sync,
                user_token=user_token,
                guild_id=guild_id,
                channel_ids=collector.channel_ids,
                after_date=after_date,
                before_date=before_date,
                collector=collector,
            )

            task_markdown_export_and_push(
                dry_run=False,
                skip_markdown_export=skip_markdown_export,
                skip_remote_push=skip_remote_push,
                guild_id=guild_id,
                collector=collector,
            )

            if skip_pinecone:
                logger.info("skipping Pinecone (--skip-pinecone)")

            logger.info("finished successfully")
            return DiscordCollectionTrackerResult(
                success=True,
                counts={
                    "messages": messages_synced,
                    "channels": (
                        len(collector.channel_ids) if collector.channel_ids else 0
                    ),
                },
            )
        except Exception as e:
            logger.exception("command failed: %s", e)
            raise
