# DiscordChatExporter (CLI setup)

This project uses **[DiscordChatExporter](https://github.com/Tyrrrz/DiscordChatExporter)** (CLI), not a separate product named “DiscordExpert.” The GUI and CLI come from the same Tyrrrz releases; ingestion here runs the **CLI** only (`export`, `exportguild`, `channels`), driven by `discord_activity_tracker/sync/chat_exporter.py` and `manage.py run_discord_activity_tracker`.

Exporter credentials and Discord server/channel IDs are configured via `.env` (see `.env.example`). User-account automation may violate Discord’s Terms of Service; prefer official APIs and bots when possible.

---

## 1. Download a release

1. Open **[DiscordChatExporter releases](https://github.com/Tyrrrz/DiscordChatExporter/releases/latest)**.
2. Download the archive for your OS:
   - **Windows:** e.g. `DiscordChatExporter.win-x64.zip` (contains `DiscordChatExporter.Cli.exe` and dependencies).
   - **macOS Apple Silicon:** e.g. `DiscordChatExporter.osx-arm64.zip`.
   - **macOS Intel:** e.g. `DiscordChatExporter.osx-x64.zip`.
   - **Linux:** pick the matching `linux-*` zip.

Official overview: [Tyrrrz/DiscordChatExporter](https://github.com/Tyrrrz/DiscordChatExporter).

---

## 2. Where to install (this repo)

Default layout (no `DISCORD_CHAT_EXPORTER_CLI` in `.env`):

| Piece | Path |
|-------|------|
| Workspace root | `{WORKSPACE_DIR}/discord_activity_tracker/` (see [Workspace.md](../Workspace.md)) |
| CLI directory | `{WORKSPACE_DIR}/discord_activity_tracker/script/` |
| Binary (Windows) | `DiscordChatExporter.Cli.exe` |
| Binary (macOS / Linux) | `DiscordChatExporter.Cli` (no extension) |

Create `script/` if it does not exist, extract the CLI **and** any bundled files from the zip into that folder, then ensure the binary is executable on Unix (`chmod +x DiscordChatExporter.Cli`).

Alternatively, install the CLI anywhere and set **`DISCORD_CHAT_EXPORTER_CLI`** in `.env` to the **absolute path** of the executable.

---

## 3. Configure environment variables

All variables live in `.env` (see `.env.example` in the repo root). The ones that matter for the CLI:

| Variable | Purpose |
|----------|---------|
| `DISCORD_SERVER_ID` | Guild snowflake to export. |
| `DISCORD_CHANNEL_IDS` | Optional comma-separated channel IDs; empty often means “all text channels” depending on exporter mode. |
| `DISCORD_CHAT_EXPORTER_CLI` | Optional absolute path to `DiscordChatExporter.Cli` / `.exe` if not using `workspace/.../script/`. |
| `DISCORD_CHAT_EXPORTER_DOTNET_DLL` | Optional path to `DiscordChatExporter.Cli.dll` — use with system `dotnet` on macOS when the bundled host fails (external disks / quarantine). |
| `DISCORD_CHAT_EXPORTER_DOTNET` | Optional explicit `dotnet` binary if not on `PATH`. |
| `DISCORD_CHAT_EXPORTER_MACOS_CLEAR_QUARANTINE` | If `true`, runs `xattr` cleanup on the CLI folder before export (only if you trust the files). |
| `DISCORD_CHAT_EXPORTER_PARALLEL` | Parallelism for `exportguild` (keep low if you hit OOM / SIGKILL). |
| `DISCORD_CHAT_EXPORTER_SEQUENTIAL_EXPORT` | When `true`, exports channels one-by-one (safer on huge guilds). |
| `DISCORD_CHAT_EXPORTER_INCLUDE_VC` | Whether to include voice channels in listings where applicable. |

Optional **.NET GC** env vars (`DOTNET_GCConserveMemory`, etc.) are documented in `.env.example`; they are forwarded into the exporter subprocess to reduce memory spikes.

---

## 4. macOS tips

- **Architecture:** Use an **arm64** build on Apple Silicon and **x64** on Intel. The code validates the binary with `file(1)` where possible and errors with a hint if the ABI is wrong.
- **External volumes / Gatekeeper:** If the native CLI fails to start, use **`DISCORD_CHAT_EXPORTER_DOTNET_DLL`** plus a system-installed **`dotnet`** SDK/runtime (`brew install dotnet`), pointing at `DiscordChatExporter.Cli.dll` next to your extracted CLI files.
- **Quarantine:** Downloaded zips may carry quarantine flags; `DISCORD_CHAT_EXPORTER_MACOS_CLEAR_QUARANTINE` or manual `xattr -cr` on the `script/` folder can help (only for trusted binaries).

---

## 5. How the project invokes it

- **`manage.py run_discord_activity_tracker`** — Runs DiscordChatExporter → parses JSON → DB → archives under `{WORKSPACE_DIR}/raw/discord_activity_tracker/<server_id>/<channel_id>/`, then optional Markdown export and Pinecone sync.
- **`manage.py backfill_discord_activity_tracker`** — Does **not** call the CLI by default in the current design: it imports JSON already placed under
  `{WORKSPACE_DIR}/discord_activity_tracker/Discussion - c-cpp-discussion/` (recursive), then deletes each file after a successful DB import. Use the CLI manually or elsewhere to produce those JSON files if needed.

For command-line flags on the Django side, see [service_api/discord_activity_tracker.md](../service_api/discord_activity_tracker.md).

---

## 6. Quick sanity check

After placing the CLI:

```bash
# Replace with your actual binary path if needed
/path/to/DiscordChatExporter.Cli --help
```

Then a dry run (no writes):

```bash
python manage.py run_discord_activity_tracker --dry-run
```

If Django reports a missing CLI or wrong architecture, follow the error text — it usually points at the releases page and expected binary name.
