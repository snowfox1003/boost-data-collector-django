"""DiscordChatExporter CLI wrapper for user token-based scraping."""

import json
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from ..workspace import get_workspace_root

_SAFE_INT_MAX = 2**63 - 1  # max safe BigIntegerField value


def _safe_int(value: object, default: int = 0) -> int:
    """Convert a snowflake string or int to int; clamp to BigIntegerField range."""
    try:
        result = int(value)  # type: ignore[arg-type]
        return result if 0 <= result <= _SAFE_INT_MAX else default
    except (TypeError, ValueError):
        return default


logger = logging.getLogger(__name__)

# Official releases (GUI + CLI); place the CLI binary locally or set DISCORD_CHAT_EXPORTER_CLI.
DISCORD_CHAT_EXPORTER_RELEASES_URL = (
    "https://github.com/Tyrrrz/DiscordChatExporter/releases/latest"
)


class DiscordChatExporterError(Exception):
    pass


def _default_cli_basename() -> str:
    """DiscordChatExporter ships ``.exe`` on Windows and extensionless ``DiscordChatExporter.Cli`` on macOS/Linux."""
    if sys.platform == "win32":
        return "DiscordChatExporter.Cli.exe"
    return "DiscordChatExporter.Cli"


def _get_parallel_workers() -> int:
    """DiscordChatExporter ``--parallel``; clamped to reduce OOM (exit -9 / SIGKILL)."""
    from django.conf import settings

    raw = int(getattr(settings, "DISCORD_CHAT_EXPORTER_PARALLEL", 1) or 1)
    return max(1, min(16, raw))


def _get_cli_path() -> Path:
    """Resolve CLI path at call time.

    Prefer ``DISCORD_CHAT_EXPORTER_CLI`` from Django settings (``.env``), otherwise
    ``workspace/discord_activity_tracker/script/`` plus the platform default binary name.
    """
    from django.conf import settings

    configured = getattr(settings, "DISCORD_CHAT_EXPORTER_CLI", None)
    if configured:
        return Path(configured).expanduser().resolve()
    return get_workspace_root() / "script" / _default_cli_basename()


def _file_command_brief_description(cli_path: Path) -> Optional[str]:
    """Return ``file -b`` output for *cli_path*, or None if unavailable."""
    file_bin = shutil.which("file")
    if not file_bin:
        return None
    try:
        proc = subprocess.run(
            [file_bin, "-b", str(cli_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return (proc.stdout or "").strip() or None


def validate_discord_chat_exporter_cli_architecture(cli_path: Path) -> None:
    """Fail fast if the CLI binary ABI clearly mismatches this machine (e.g. Intel build on Apple Silicon).

    Uses ``file(1)`` on Unix when present. Universal binaries containing both slices pass.
    """
    if sys.platform == "win32":
        return

    host = platform.machine().lower()
    host_is_arm = host in ("arm64", "aarch64")
    host_is_intel = host in ("x86_64", "amd64", "i386", "i686")

    desc = _file_command_brief_description(cli_path)
    if not desc:
        logger.debug(
            "DiscordChatExporter arch check skipped (no `file` output for %s)",
            cli_path,
        )
        return

    d = desc.lower()
    has_arm = "arm64" in d or "aarch64" in d
    has_intel = "x86_64" in d or "i386" in d or "i686" in d or "amd64" in d

    if host_is_arm and has_intel and not has_arm:
        raise DiscordChatExporterError(
            f"DiscordChatExporter binary is Intel-only ({desc!r}) but this host is "
            f"{platform.machine()} (use the osx-arm64 / linux-arm64 build from "
            f"{DISCORD_CHAT_EXPORTER_RELEASES_URL})."
        )
    if host_is_intel and has_arm and not has_intel:
        raise DiscordChatExporterError(
            f"DiscordChatExporter binary is arm64-only ({desc!r}) but this host is "
            f"{platform.machine()} (use the osx-x64 / linux-x64 build from "
            f"{DISCORD_CHAT_EXPORTER_RELEASES_URL})."
        )

    logger.info(
        "DiscordChatExporter CLI arch check OK (host=%s, file(1)=%s)",
        platform.machine(),
        desc,
    )


def _utc_wall_clock_for_cli(dt: datetime) -> datetime:
    """Normalize to UTC for ``--after`` / ``--before`` strings (DiscordChatExporter uses UTC wall clock)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _get_include_voice_channels() -> bool:
    from django.conf import settings

    return bool(getattr(settings, "DISCORD_CHAT_EXPORTER_INCLUDE_VC", False))


def _get_sequential_export() -> bool:
    from django.conf import settings

    return bool(getattr(settings, "DISCORD_CHAT_EXPORTER_SEQUENTIAL_EXPORT", False))


def _cli_argv_head(cli_path: Path) -> list[str]:
    """First argv token(s) for the exporter: native binary, or ``dotnet`` + ``.dll``."""
    from django.conf import settings

    raw = getattr(settings, "DISCORD_CHAT_EXPORTER_DOTNET_DLL", None)
    if raw and str(raw).strip():
        dll = Path(str(raw).strip()).expanduser().resolve()
        if not dll.exists():
            raise DiscordChatExporterError(
                f"DISCORD_CHAT_EXPORTER_DOTNET_DLL points to a missing file: {dll}"
            )
        dotnet_raw = getattr(settings, "DISCORD_CHAT_EXPORTER_DOTNET", None)
        dotnet_bin = (
            (str(dotnet_raw).strip() if dotnet_raw else "")
            or shutil.which("dotnet")
            or ""
        )
        if not dotnet_bin:
            raise DiscordChatExporterError(
                "DISCORD_CHAT_EXPORTER_DOTNET_DLL is set but `dotnet` was not found. "
                "Install the .NET runtime (e.g. `brew install dotnet`) or set "
                "DISCORD_CHAT_EXPORTER_DOTNET to the full path of the `dotnet` executable."
            )
        resolved_dotnet = Path(dotnet_bin).expanduser().resolve()
        return [str(resolved_dotnet), str(dll)]
    return [str(cli_path)]


def _maybe_macos_clear_quarantine(bundle_dir: Path) -> None:
    """Optionally strip extended attributes (e.g. quarantine) from the CLI bundle directory."""
    from django.conf import settings

    if sys.platform != "darwin":
        return
    if not getattr(settings, "DISCORD_CHAT_EXPORTER_MACOS_CLEAR_QUARANTINE", False):
        return
    xattr_bin = shutil.which("xattr")
    if not xattr_bin:
        logger.warning(
            "DISCORD_CHAT_EXPORTER_MACOS_CLEAR_QUARANTINE is true but `xattr` was not found"
        )
        return
    try:
        subprocess.run(
            [xattr_bin, "-cr", str(bundle_dir)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("xattr -cr failed for %s: %s", bundle_dir, e)
        return
    logger.info(
        "Ran `xattr -cr` on %s (DISCORD_CHAT_EXPORTER_MACOS_CLEAR_QUARANTINE)",
        bundle_dir,
    )


def _stderr_macos_hostfxr_hints(stderr: str, *, cli_path: Path | None) -> str:
    if sys.platform != "darwin":
        return ""
    s = stderr.lower()
    if not (
        "libhostfxr" in s
        or "library load disallowed by system policy" in s
        or ("not valid for use in process" in s and "code signature" in s)
    ):
        return ""
    script_dir = cli_path.parent if cli_path is not None else Path(".")
    return (
        "\nmacOS blocked the bundled .NET host library (libhostfxr). Typical fixes:\n"
        f"  • Clear quarantine: xattr -cr {script_dir}\n"
        "  • If the project lives on an external disk (/Volumes/...), copy "
        "workspace/discord_activity_tracker/script/ to your internal SSD and set "
        "DISCORD_CHAT_EXPORTER_CLI (and optionally DISCORD_CHAT_EXPORTER_DOTNET_DLL) to that copy.\n"
        "  • Or install .NET (`brew install dotnet`) and set DISCORD_CHAT_EXPORTER_DOTNET_DLL to the "
        "full path of DiscordChatExporter.Cli.dll next to the CLI (runs via system `dotnet`)."
    )


def _exporter_subprocess_env() -> dict[str, str]:
    result = {
        k: v
        for k, v in os.environ.items()
        if k.lower() not in ("http_proxy", "https_proxy")
    }
    # Reduce .NET runtime memory usage to avoid macOS jetsam SIGKILL (-9).
    # These are setdefault so any value already in the environment takes precedence.
    #
    # DOTNET_GCConserveMemory=9  – most aggressive GC compaction (range 0-9).
    # DOTNET_GCHighMemPercent=50 – start aggressive GC when machine RAM hits 50 %
    #                               (default 90 %; lower = earlier pressure-relief).
    # DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1 – skip loading the ICU data library
    #                               (saves ~50-150 MB at startup; OK for plain ASCII
    #                               channel names used by DiscordChatExporter output).
    result.setdefault("DOTNET_GCConserveMemory", "9")
    result.setdefault("DOTNET_GCHighMemPercent", "50")
    result.setdefault("DOTNET_SYSTEM_GLOBALIZATION_INVARIANT", "1")
    return result


def _cli_bool(value: bool) -> str:
    return "True" if value else "False"


def _log_redacted_command(cmd: Sequence[str]) -> None:
    safe: List[str] = []
    i = 0
    while i < len(cmd):
        if i + 1 < len(cmd) and cmd[i] == "--token":
            safe.extend(["--token", "<redacted>"])
            i += 2
        else:
            safe.append(str(cmd[i]))
            i += 1
    logger.debug("Command: %s", " ".join(safe))


def _sigkill_suffix() -> str:
    return (
        " (SIGKILL: often out-of-memory or macOS memory pressure; "
        "set DISCORD_CHAT_EXPORTER_PARALLEL=1, DISCORD_CHAT_EXPORTER_INCLUDE_VC=false; "
        "try DISCORD_CHAT_EXPORTER_SEQUENTIAL_EXPORT=true for one channel per CLI process; "
        "with sequential export, set DISCORD_CHANNEL_IDS (or --channels) to skip the "
        "heavy `channels` listing step; "
        "the subprocess already sets DOTNET_GCConserveMemory=9 / DOTNET_GCHighMemPercent=50 / "
        "DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1 by default — override in your shell env if needed; "
        "also run: xattr -d com.apple.quarantine <cli_path> if the binary was downloaded)"
    )


def _raise_cli_failure(
    *,
    op: str,
    returncode: int | None,
    stderr: str,
    cli_path: Path | None = None,
) -> None:
    error_msg = f"DiscordChatExporter {op} failed with exit code {returncode}"
    if returncode == -9:
        error_msg += _sigkill_suffix()
    if stderr.strip():
        error_msg += f"\nError: {stderr.strip()}"
    error_msg += _stderr_macos_hostfxr_hints(stderr, cli_path=cli_path)
    logger.error(error_msg)
    raise DiscordChatExporterError(error_msg)


def parse_channels_command_stdout(text: str) -> List[int]:
    """Parse ``channels`` subcommand stdout into channel snowflake IDs (excludes thread lines)."""
    ids: List[int] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("*"):
            continue
        m = re.match(r"^(\d+)\s+\|", line)
        if m:
            ids.append(int(m.group(1)))
    return ids


def _run_channels_listing(
    cli_path: Path,
    user_token: str,
    guild_id: int,
    include_threads: str,
) -> List[int]:
    cmd = _cli_argv_head(cli_path) + [
        "channels",
        "--token",
        user_token,
        "--guild",
        str(guild_id),
        "--include-vc",
        _cli_bool(_get_include_voice_channels()),
        "--include-threads",
        include_threads,
    ]
    _log_redacted_command(cmd)
    proc = subprocess.run(
        cmd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_exporter_subprocess_env(),
        check=False,
    )
    stderr = proc.stderr or ""
    if proc.returncode != 0:
        _raise_cli_failure(
            op="channels",
            returncode=proc.returncode,
            stderr=stderr,
            cli_path=cli_path,
        )
    return parse_channels_command_stdout(proc.stdout or "")


def _run_exporter_streaming(cmd: list[str], *, cli_path: Path) -> None:
    _log_redacted_command(cmd)
    try:
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_exporter_subprocess_env(),
        )
        for line in process.stdout or []:
            line = line.rstrip()
            if line:
                logger.info("[CLI] %s", line)
        process.wait()
        stderr = process.stderr.read() if process.stderr else ""
        if process.returncode != 0:
            _raise_cli_failure(
                op="export",
                returncode=process.returncode,
                stderr=stderr,
                cli_path=cli_path,
            )
    except DiscordChatExporterError:
        raise
    except OSError as e:
        if getattr(e, "errno", None) == 8 and sys.platform != "win32":
            raise DiscordChatExporterError(
                f"Cannot run {cli_path} on {sys.platform} (wrong executable format). "
                "Use the macOS or Linux build from "
                f"{DISCORD_CHAT_EXPORTER_RELEASES_URL} "
                f"(`{_default_cli_basename()}`), or set DISCORD_CHAT_EXPORTER_CLI to that binary."
            ) from e
        logger.exception("Unexpected error running DiscordChatExporter: %s", e)
        raise DiscordChatExporterError(f"Unexpected error: {e}") from e
    except Exception as e:
        logger.exception("Unexpected error running DiscordChatExporter: %s", e)
        raise DiscordChatExporterError(f"Unexpected error: {e}") from e


def _append_export_window(
    cmd: list[str],
    after_date: Optional[datetime],
    before_date: Optional[datetime],
) -> None:
    if after_date:
        after_utc = _utc_wall_clock_for_cli(after_date)
        after_str = after_utc.strftime("%Y-%m-%d %H:%M:%S")
        cmd.extend(["--after", after_str])
        logger.info(
            "Incremental sync: exporting messages after %s UTC (DiscordChatExporter --after)",
            after_str,
        )
    if before_date:
        before_utc = _utc_wall_clock_for_cli(before_date)
        before_str = before_utc.strftime("%Y-%m-%d %H:%M:%S")
        cmd.extend(["--before", before_str])
        logger.info(
            "Exporting messages before %s UTC (DiscordChatExporter --before)",
            before_str,
        )


def _export_guild_sequential(
    cli_path: Path,
    user_token: str,
    guild_id: int,
    output_dir: Path,
    after_date: Optional[datetime],
    before_date: Optional[datetime],
    include_threads: str,
    channel_ids: Optional[Sequence[int]],
) -> List[Path]:
    logger.info(
        "DiscordChatExporter sequential mode (DISCORD_CHAT_EXPORTER_SEQUENTIAL_EXPORT)"
    )
    if channel_ids:
        seen: set[int] = set()
        ids: List[int] = []
        for i in channel_ids:
            if i not in seen:
                seen.add(i)
                ids.append(i)
        logger.info(
            "Skipping DiscordChatExporter `channels` listing (%d explicit id(s)); "
            "export runs directly (avoids OOM/SIGKILL on huge guilds)",
            len(ids),
        )
    else:
        raw_ids = _run_channels_listing(
            cli_path, user_token, guild_id, include_threads=include_threads
        )
        ids = list(raw_ids)
    if not ids:
        raise DiscordChatExporterError(
            "No channels to export after listing the guild (check DISCORD_CHANNEL_IDS / "
            "--channels filter, token access, or INCLUDE_VC if you need voice channels)."
        )
    logger.info("Exporting %d channel(s) one process at a time", len(ids))
    for ch_id in ids:
        # `export` (per-channel) does not support --include-threads or --respect-rate-limits
        # in DiscordChatExporter 2.40+; thread inclusion applies to `channels` / `exportguild` only.
        cmd = _cli_argv_head(cli_path) + [
            "export",
            "--token",
            user_token,
            "--channel",
            str(ch_id),
            "--output",
            str(output_dir) + os.sep,
            "--format",
            "Json",
            "--parallel",
            "1",
            "--markdown",
            "True",
        ]
        _append_export_window(cmd, after_date, before_date)
        logger.info("Running DiscordChatExporter export for channel %s", ch_id)
        _run_exporter_streaming(cmd, cli_path=cli_path)
    logger.info("Sequential export completed successfully")


def _export_guild_exportguild(
    cli_path: Path,
    user_token: str,
    guild_id: int,
    output_dir: Path,
    after_date: Optional[datetime],
    before_date: Optional[datetime],
    include_threads: str,
) -> None:
    cmd = _cli_argv_head(cli_path) + [
        "exportguild",
        "--token",
        user_token,
        "--guild",
        str(guild_id),
        "--output",
        str(output_dir) + os.sep,
        "--format",
        "Json",
        "--include-threads",
        include_threads,
        "--include-vc",
        _cli_bool(_get_include_voice_channels()),
        "--parallel",
        str(_get_parallel_workers()),
        "--markdown",
        "True",
    ]
    _append_export_window(cmd, after_date, before_date)
    logger.info("Running DiscordChatExporter exportguild for guild %s", guild_id)
    _run_exporter_streaming(cmd, cli_path=cli_path)
    logger.info("Exportguild completed successfully")


def filter_discord_export_json_paths(paths: Iterable[Path]) -> List[Path]:
    """Exclude macOS AppleDouble resource-fork files (``._*.json``); they are not UTF-8 JSON."""
    return [p for p in paths if not p.name.startswith("._")]


def _sorted_discord_export_json_paths(output_dir: Path) -> List[Path]:
    """``*.json`` from DiscordChatExporter, excluding macOS AppleDouble sidecars (``._*``)."""
    return sorted(filter_discord_export_json_paths(output_dir.glob("*.json")))


def export_guild_to_json(
    user_token: str,
    guild_id: int,
    output_dir: Path,
    after_date: Optional[datetime] = None,
    before_date: Optional[datetime] = None,
    include_threads: str = "None",
    channel_ids: Optional[Sequence[int]] = None,
) -> List[Path]:
    """Export all channels from a guild. Returns list of JSON file paths."""
    from django.conf import settings

    cli_path = _get_cli_path()
    dotnet_dll_setting = getattr(settings, "DISCORD_CHAT_EXPORTER_DOTNET_DLL", None)
    use_dotnet = bool((dotnet_dll_setting or "").strip())

    if use_dotnet:
        dll_path = Path(str(dotnet_dll_setting).strip()).expanduser().resolve()
        if not dll_path.exists():
            raise DiscordChatExporterError(
                f"DISCORD_CHAT_EXPORTER_DOTNET_DLL points to a missing file: {dll_path}"
            )
        _maybe_macos_clear_quarantine(dll_path.parent)
    else:
        if not cli_path.exists():
            raise DiscordChatExporterError(
                f"DiscordChatExporter CLI not found at {cli_path}. "
                f"Download from {DISCORD_CHAT_EXPORTER_RELEASES_URL} "
                "(e.g. DiscordChatExporter.Cli.osx-arm64.zip or .osx-x64.zip on Mac; "
                ".linux-*.zip on Linux; .exe on Windows). "
                "Extract next to the executable, put it under "
                "workspace/discord_activity_tracker/script/, "
                "or set DISCORD_CHAT_EXPORTER_CLI in .env to the full path of the CLI."
            )
        _maybe_macos_clear_quarantine(cli_path.parent)
        validate_discord_chat_exporter_cli_architecture(cli_path)

    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        if _get_sequential_export():
            _export_guild_sequential(
                cli_path,
                user_token,
                guild_id,
                output_dir,
                after_date,
                before_date,
                include_threads,
                channel_ids,
            )
        else:
            _export_guild_exportguild(
                cli_path,
                user_token,
                guild_id,
                output_dir,
                after_date,
                before_date,
                include_threads,
            )
    except DiscordChatExporterError:
        raise
    except OSError as e:
        if getattr(e, "errno", None) == 8 and sys.platform != "win32":
            raise DiscordChatExporterError(
                f"Cannot run {cli_path} on {sys.platform} (wrong executable format). "
                "Use the macOS or Linux build from "
                f"{DISCORD_CHAT_EXPORTER_RELEASES_URL} "
                f"(`{_default_cli_basename()}`), or set DISCORD_CHAT_EXPORTER_CLI to that binary."
            ) from e
        logger.exception("Unexpected error running DiscordChatExporter: %s", e)
        raise DiscordChatExporterError(f"Unexpected error: {e}") from e
    except Exception as e:
        logger.exception("Unexpected error running DiscordChatExporter: %s", e)
        raise DiscordChatExporterError(f"Unexpected error: {e}") from e

    json_files = _sorted_discord_export_json_paths(output_dir)
    logger.info("Found %d exported JSON files", len(json_files))
    return json_files


def parse_exported_json(json_path: Path) -> Dict[str, Any]:
    """Parse a DiscordChatExporter JSON file into a dict with guild, channel, messages."""
    logger.debug(f"Parsing {json_path.name}")

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return data

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON from {json_path}: {e}")
        raise
    except Exception as e:
        logger.exception(f"Error reading {json_path}: {e}")
        raise


def convert_exporter_message_to_dict(msg_data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert DiscordChatExporter message format to our internal format.

    Key normalizations applied here:
    - All snowflake IDs coerced from string → int via _safe_int.
    - Reaction emoji extracted from nested {"name": ...} dict to plain string.
    - Author avatarUrl mapped to avatar_url.
    - message_type and is_pinned mapped from DiscordChatExporter fields.
    """
    author = msg_data.get("author", {})

    converted = {
        "id": _safe_int(msg_data.get("id", 0)),
        "content": msg_data.get("content", ""),
        "created_at": msg_data.get("timestamp", ""),
        "edited_at": msg_data.get("timestampEdited"),
        "message_type": msg_data.get("type", "Default") or "Default",
        "is_pinned": bool(msg_data.get("isPinned", False)),
        "author": {
            "id": _safe_int(author.get("id", 0)),
            "username": author.get("name", "unknown") or "unknown",
            "global_name": author.get("nickname") or author.get("name", "unknown"),
            "avatar_url": author.get("avatarUrl", ""),
            "bot": bool(author.get("isBot", False)),
        },
        "attachments": [
            {"url": att.get("url")} for att in msg_data.get("attachments", [])
        ],
        "reactions": [
            {
                "emoji": (reaction.get("emoji") or {}).get("name") or "",
                "count": reaction.get("count", 0),
            }
            for reaction in msg_data.get("reactions", [])
        ],
        "reference": None,
    }

    if msg_data.get("reference"):
        ref = msg_data["reference"]
        ref_id = ref.get("messageId") or ref.get("message_id")
        converted["reference"] = {"message_id": _safe_int(ref_id) if ref_id else None}

    return converted


def export_and_parse_guild(
    user_token: str,
    guild_id: int,
    output_dir: Path,
    after_date: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Export guild via CLI and parse all resulting JSON files."""
    json_files = export_guild_to_json(
        user_token=user_token,
        guild_id=guild_id,
        output_dir=output_dir,
        after_date=after_date,
    )

    json_files = filter_discord_export_json_paths(json_files)

    parsed_channels = []

    for json_path in json_files:
        try:
            data = parse_exported_json(json_path)

            parsed_channels.append(
                {
                    "guild": data.get("guild", {}),
                    "channel": data.get("channel", {}),
                    "messages": data.get("messages", []),
                    "file_path": json_path,
                }
            )

        except Exception as e:
            logger.error(f"Failed to process {json_path.name}: {e}")
            continue

    return parsed_channels
