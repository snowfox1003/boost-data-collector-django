# DiscordChatExporter (CLI setup)

This project uses **[DiscordChatExporter](https://github.com/Tyrrrz/DiscordChatExporter)** (CLI), not a separate product named “DiscordExpert.” The GUI and CLI come from the same Tyrrrz releases; ingestion here runs the **CLI** only (`export`, `exportguild`, `channels`), driven by `discord_activity_tracker/sync/chat_exporter.py` and `manage.py run_discord_activity_tracker`.

Using a **user token** with DiscordChatExporter may violate Discord’s Terms of Service; prefer official APIs / bots when possible. Document tokens securely and never commit them.

---

## Discord token and IDs (for fetching)

`manage.py run_discord_activity_tracker` reads **`DISCORD_USER_TOKEN`** from `.env`. DiscordChatExporter uses the same kind of value as its CLI **`-t`** / `--token` argument when talking to Discord.

### Where to get the token

Discord does **not** publish a supported “export my user token” flow for this use case. **Follow the maintained upstream guide** (it is updated when the Discord client or API changes):

- **[Token and IDs](https://github.com/Tyrrrz/DiscordChatExporter/blob/master/.docs/Token-and-IDs.md)** — how to obtain a token and copy **server** / **channel** snowflake IDs.

**Built-in CLI help** (after you install the binary, see below):

- **macOS / Linux:** `./DiscordChatExporter.Cli guide`
- **Windows (`cmd`):** `DiscordChatExporter.Cli.exe guide` (no leading `./`)

That command prints the same class of instructions as the wiki.

Put the token in **`.env`** (never commit it):

```env
DISCORD_USER_TOKEN=your_token_here
```

### Bot token vs user token

| Item | Env var in this repo | Used by ChatExporter fetch? |
|------|----------------------|----------------------------|
| **User** (account) token | `DISCORD_USER_TOKEN` | **Yes** — required for `run_discord_activity_tracker` → DiscordChatExporter. |
| **Bot** token from the [Developer Portal](https://discord.com/developers/applications) | `DISCORD_TOKEN` | **No** for this exporter path (reserved for other / future bot-based features). |

If export fails with “unauthorized” or similar, double-check you pasted the **user** token, not a bot token, and that the value has no extra quotes or spaces.

### Server and channel IDs

Set **`DISCORD_SERVER_ID`** to the guild you want. Optionally set **`DISCORD_CHANNEL_IDS`** to a comma-separated list of channel snowflakes; leave empty when you want the exporter to include all relevant channels (see behavior in [service_api/discord_activity_tracker.md](../service_api/discord_activity_tracker.md)). **Developer Mode** in the Discord app (Settings → Advanced) enables **Copy ID** on servers and channels; details are in **Token and IDs** above.

### If the token leaks

Treat it like a password. Revoke or rotate it using the same upstream steps you used to obtain it, and follow [Discord’s account security guidance](https://support.discord.com/hc/en-us/categories/360001371893-Account-Security-Verification). Do not paste tokens into chat, tickets, or screenshots.

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
| `DISCORD_USER_TOKEN` | Token passed to DiscordChatExporter for export (required for `run_discord_activity_tracker` fetch path). |
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
