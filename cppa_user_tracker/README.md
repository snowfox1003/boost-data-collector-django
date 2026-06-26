# CPPA User Tracker

## Overview

**Identity and profiles for CPPA workflows** — GitHub accounts, Slack profiles, mailing identities, staging rows, and helpers other apps call while they ingest. This app is **not** a standalone “hit an API and fill the DB” collector today.

**`run_cppa_user_tracker`** is still a **stub** (it logs and exits successfully). **Real writes** happen when **other apps** import [`services.py`](services.py) during Slack, GitHub, mailing list, or similar runs.

**Docs:** [docs/service_api/cppa_user_tracker.md](../docs/service_api/cppa_user_tracker.md) · [docs/Schema.md, section 1 — Base tables, Identity, and profiles](../docs/Schema.md#1-base-tables-identity-and-profiles) · [`models.py`](models.py)

## What lives in this app

| Piece | Role |
| --- | --- |
| **ORM models** | `Identity`, profiles (`BaseProfile` subclasses), `GitHubAccount`, `Email`, staging (`TmpIdentity`, `TempProfileIdentityRelation`), and related linkage — see Schema §1. |
| **`services.py`** | **Primary API** for get-or-create and updates; called from other collectors, not only from this app’s management command. |
| **`run_cppa_user_tracker`** | Placeholder scheduled entrypoint until staging/merge logic is implemented. |

## How data gets into the database

1. **Upstream collectors** (e.g. [`cppa_slack_tracker`](../cppa_slack_tracker/README.md), [`github_activity_tracker`](../github_activity_tracker/README.md)) call the network and parse payloads.
2. They invoke **`cppa_user_tracker.services`** helpers to **upsert** users, accounts, and profile rows this app owns.
3. **`run_cppa_user_tracker`** does **not** perform that fetch path yet; keep it in the schedule only if you want a no-op heartbeat until real logic ships.

## What this app does *not* do (today)

- **No dedicated external fetch** in the management command — no Slack/GitHub client owned solely by this stub.
- **No Markdown or git push** from `run_cppa_user_tracker`.
- **No Pinecone** — no call to [`cppa_pinecone_sync`](../cppa_pinecone_sync/README.md); if you add identity-aware search later, add a preprocessor and call `run_cppa_pinecone_sync` per [docs/Pinecone_preprocess_guideline.md](../docs/Pinecone_preprocess_guideline.md).

## Common tasks

- Inspect or extend writes: read [`services.py`](services.py) and [docs/service_api/cppa_user_tracker.md](../docs/service_api/cppa_user_tracker.md).
- Smoke the stub: `python manage.py run_cppa_user_tracker --help`.
- Missing tables locally: run migrations (root [README](../README.md#initial-setup)).

## Main command: `run_cppa_user_tracker`

Collector **stub** — validates the `BaseCollectorCommand` wiring and prints success; **no** custom CLI flags yet beyond Django defaults (`--verbosity`, etc.).

| Option | Description |
| --- | --- |
| _(none)_ | No app-specific arguments until staging/merge work adds them. |

## Management commands

| Command | Purpose |
| --- | --- |
| `run_cppa_user_tracker` | Scheduled placeholder for future identity/staging pipeline. |

Run `python manage.py COMMAND --help` for options.

## Tests

```bash
python -m pytest cppa_user_tracker/tests/ -v
```

(from repo root; see root [README](../README.md#running-tests).)
