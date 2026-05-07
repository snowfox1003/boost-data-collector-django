# Workspace: one folder, subfolders per app

The project uses a **single workspace directory** for raw and processed files (cloned repos, downloaded PDFs, converted output, etc.). Each app that needs file space has its own **subfolder** under that root.

## Layout

```
workspace/                                    # WORKSPACE_DIR (configurable via env)
├── github_activity_tracker/                  # JSON cache for sync (see below)
│   └── <owner>/<repo>/
│       ├── commits/<hash>.json
│       ├── issues/<issue_number>.json
│       └── prs/<pr_number>.json
├── boost_library_tracker/                    # PDFs, converted files, etc.
├── raw/
│   ├── github_activity_tracker/             # Raw GitHub API responses (llvm/llvm-project from clang_github_tracker; kept)
│   │   └── <owner>/<repo>/
│   │       ├── commits/<sha>.json
│   │       ├── issues/<number>.json
│   │       └── prs/<number>.json
│   └── boost_mailing_list_tracker/           # Raw API responses (kept, not removed)
│       └── <list_name>/<msg_id>.json
│   └── discord_activity_tracker/             # DiscordChatExporter output (see below)
│       ├── _exporter_staging/                # Temporary guild export (cleared each run)
│       └── <server_id>/<channel_id>/         # Archived JSON after DB import
├── clang_github_tracker/                    # Markdown export for clang_github_tracker (md_export/)
├── boost_mailing_list_tracker/               # Mailing list messages (see below)
│   └── <list_name>/
│       └── messages/<msg_id>.json            # Formatted cache (processed then removed)
├── discord_activity_tracker/                 # CLI install + backfill drop folder
│   ├── script/                               # DiscordChatExporter.Cli (default layout; optional)
│   └── Discussion - c-cpp-discussion/      # Pre-exported JSON for backfill (removed after import)
└── shared/                                   # Temp files used by more than one app
```

### github_activity_tracker sync flow

1. **Process existing JSONs** – For each repo, load every `commits/*.json`, `issues/*.json`, `prs/*.json` in that repo's workspace folder, write to the database, then **remove** the file.
2. **Fetch from GitHub** – Fetch commits, issues, and PRs from the API; for each item **save as JSON** in the path above.
3. **Persist and remove** – After saving an item to the database, **remove** its JSON file.

So the workspace acts as a short-lived cache: files are deleted once they are in the DB.

### boost_mailing_list_tracker sync flow

1. **Process existing JSONs** – For each list, load every `messages/*.json` in that list's workspace folder, write to the database, then **remove** the file.
2. **Fetch from API** – Fetch emails from Boost mailing list archives. For each item: **save raw API response** to `workspace/raw/boost_mailing_list_tracker/<list_name>/<msg_id>.json` (these **raw** files are **not** removed). Then save formatted data to `workspace/boost_mailing_list_tracker/<list_name>/messages/<msg_id>.json`, persist to DB, and remove the formatted file.
3. **start_date** – If `start_date` is not provided, the fetcher uses the day after the latest `sent_at` in the database so only new emails are fetched.

So: **raw/** = permanent archive of scraped API responses; **messages/** = short-lived cache (removed after DB persist).

### discord_activity_tracker paths

1. **`run_discord_activity_tracker`** — DiscordChatExporter writes to `raw/discord_activity_tracker/_exporter_staging/`, then JSON is parsed, upserted into the DB, and **moved** under `raw/discord_activity_tracker/<server_id>/<channel_id>/` (kept as an archive).
2. **`backfill_discord_activity_tracker`** — Place DiscordChatExporter JSON under `discord_activity_tracker/Discussion - c-cpp-discussion/` (any depth). Each file is imported, then **deleted** so it is not processed twice.

See [service_api/discord_activity_tracker.md](service_api/discord_activity_tracker.md) and [operations/discord_chat_exporter.md](operations/discord_chat_exporter.md).

## Configuration

- **Setting:** `settings.WORKSPACE_DIR` (default: project root `workspace/`).
- **Env:** Set `WORKSPACE_DIR` in `.env` to use another path (e.g. `/data/workspace`).

## Usage in code

**github_activity_tracker** (paths and iterators):

```python
from github_activity_tracker.workspace import (
    get_workspace_root,
    get_repo_dir,
    get_commit_json_path,
    get_issue_json_path,
    get_pr_json_path,
    iter_existing_commit_jsons,
    iter_existing_issue_jsons,
    iter_existing_pr_jsons,
)

# App workspace root (e.g. workspace/github_activity_tracker/)
root = get_workspace_root()

# Repo dir: workspace/github_activity_tracker/<owner>/<repo>/
repo_dir = get_repo_dir("boostorg", "boost")

# Paths for JSON files (commits/<hash>.json, issues/<number>.json, prs/<number>.json)
path = get_commit_json_path("boostorg", "boost", "abc123")
path = get_issue_json_path("boostorg", "boost", 42)
path = get_pr_json_path("boostorg", "boost", 10)

# Iterate existing JSON files (for "process workspace first" step)
for json_path in iter_existing_commit_jsons("boostorg", "boost"):
    ...
```

**boost_mailing_list_tracker** (paths and iterators):

```python
from boost_mailing_list_tracker.workspace import (
    get_workspace_root,
    get_list_dir,
    get_messages_dir,
    get_message_json_path,
    iter_existing_message_jsons,
)

# App workspace root (e.g. workspace/boost_mailing_list_tracker/)
root = get_workspace_root()

# List dir: workspace/boost_mailing_list_tracker/<list_name>/
list_dir = get_list_dir("boost@lists.boost.org")

# Path for message JSON: .../messages/<msg_id_safe>.json
path = get_message_json_path("boost@lists.boost.org", "abc123")

# Raw API responses (kept, not removed): workspace/raw/boost_mailing_list_tracker/<list_name>/<msg_id_safe>.json
from boost_mailing_list_tracker.workspace import get_raw_json_path
raw_path = get_raw_json_path("boost@lists.boost.org", "abc123")

# Iterate existing message JSONs for a list (for "process workspace first" step)
for json_path in iter_existing_message_jsons("boost@lists.boost.org"):
    ...
```

**discord_activity_tracker** (raw archive, staging, backfill folder):

```python
from discord_activity_tracker.workspace import (
    get_workspace_root,
    get_raw_dir,
    get_exporter_staging_dir,
    get_channel_raw_dir,
    get_cpp_discussion_import_dir,
)

# workspace/discord_activity_tracker/ (CLI script/, backfill drop folder)
app_root = get_workspace_root()

# workspace/raw/discord_activity_tracker/ (archived per-channel JSON)
raw_root = get_raw_dir()

# Staging dir used before per-channel archival
staging = get_exporter_staging_dir()

# workspace/raw/discord_activity_tracker/<server_id>/<channel_id>/
channel_dir = get_channel_raw_dir(server_id=123, channel_id=456)

# Backfill import root: .../Discussion - c-cpp-discussion/
drop = get_cpp_discussion_import_dir()
```

**Generic (any app):**

```python
from django.conf import settings
from config.workspace import get_workspace_path

path = get_workspace_path("github_activity_tracker")
path = get_workspace_path("boost_library_tracker")
pdf_dir = path / "pdfs"

# Root (for custom layout)
root = Path(settings.WORKSPACE_DIR)
```

## Migrating from legacy layout

If your workspace uses the legacy structure (commits: `<owner>/commits/<repo>/master/` or `.../developer/`; issues: `<owner>/issues/<repo>/issue_<n>.json`; prs: `<owner>/prs/<repo>/pr_<n>.json`), run:

```bash
python manage.py migrate_workspace_layout
```

Use `--dry-run` to see what would be moved without changing files. For commits, the command prefers `master/`; if `master/` is missing it uses `developer/` (the `developer/` folder is ignored when `master/` exists).

## Orphan temp files

If a collector crashes between write and delete, leftover `*.tmp`, `*.part`, `*.lock`, or `*.swp` files may remain. Run:

```bash
python manage.py cleanup_workspace_orphans
```

By default this **dry-runs** (lists candidates). Use `--execute` to delete files older than `--max-age-hours` (default: 24).

## Conventions

- **github_activity_tracker:** JSON cache for commits, issues, and PRs; files are removed after being saved to the DB.
- **boost_mailing_list_tracker:** JSON cache for mailing list messages; files are removed after being saved to the DB.
- **discord_activity_tracker:** Exporter CLI under `discord_activity_tracker/script/` (or `DISCORD_CHAT_EXPORTER_CLI`); **raw/** subtree keeps archived exports; backfill JSON in `Discussion - c-cpp-discussion/` is deleted after import.
- **boost_library_tracker:** Downloaded PDFs, converted documents.
- **shared:** Files that multiple apps read or write; clean up when no longer needed.

The `workspace/` directory is in `.gitignore`; do not commit its contents.
