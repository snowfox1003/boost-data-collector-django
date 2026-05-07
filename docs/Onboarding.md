# Onboarding: Boost Data Collector

This guide orients new contributors in one sitting: how the repo is organized, what is shared versus app-specific, where data flows, and how to extend the system without reverse‑engineering every Django app.

For setup steps (venv, migrate, tests), start with the root **[README.md](../README.md)** and **[Development_guideline.md](Development_guideline.md)**.

---

## 1. Mental model (five ideas)

1. **One Django project, one database** — All installed apps share PostgreSQL (`boost_dashboard`). There is no per-app database isolation.
2. **Collectors are management commands** — Scheduled work is `python manage.py <command>`. Production batches run **`run_scheduled_collectors`**, which reads **`config/boost_collector_schedule.yaml`** (see **[Workflow.md](Workflow.md)**).
3. **Writes go through `services.py`** — For apps that define models, creates/updates/deletes belong in that app’s **`services.py`**. Commands, fetchers, and other apps call those functions; they do not write models ad hoc (see **[Contributing.md](Contributing.md)**).
4. **Shared “collector contract” lives in `core`** — **`CollectorBase`** + **`BaseCollectorCommand`** give a consistent `run()` / `sync_pinecone()` / error-handling shape. Not every command uses them yet; new collectors should (see **[Core_public_API.md](Core_public_API.md)** and **[How_to_add_a_collector.md](How_to_add_a_collector.md)**).
5. **Cross-app coupling is intentionally loose** — Avoid **ForeignKeys** from one tracker app into another’s models when it would create tight coupling or import cycles. Prefer querying by IDs or shared reference tables (e.g. **Language**, **Identity**) as documented in **[Schema.md](Schema.md)** and **[Development_guideline.md](Development_guideline.md)**.

---

## 2. Read this first (suggested order)

| Order | Doc | Why |
|-------|-----|-----|
| 1 | [README.md](../README.md) | Prerequisites, setup, tests. |
| 2 | [Architecture_data_flow.md](Architecture_data_flow.md) | Sources → collectors → DB / workspace → Pinecone. |
| 3 | [Workflow.md](Workflow.md) | YAML schedules, Celery Beat, execution order. |
| 4 | [Contributing.md](Contributing.md) | Service-layer rule for DB writes. |
| 5 | [Workspace.md](Workspace.md) | Where files land under `WORKSPACE_DIR`. |
| 6 | [Schema.md](Schema.md) — § Overview + diagrams for your area | Cross-app tables (identity, GitHub, Boost libraries). |
| 7 | [Service_API.md](Service_API.md) + `service_api/<app>.md` | Callable surface for writes you must use. |
| 8 | [operations/README.md](operations/README.md) | Shared I/O (GitHub, etc.), not the same as services. |

Deep dives when you touch an area: **[Docker.md](Docker.md)**, **[Deployment.md](Deployment.md)**, per-app notes under **`docs/service_api/`** and **`docs/operations/`**.

---

## 3. Project apps at a glance

These are the Django apps under **`INSTALLED_APPS`** (excluding `django.contrib.*`). Use this table to **pick where your change belongs** and **which doc to open**.

| App | Role | Typical entry / notes |
|-----|------|------------------------|
| **core** | Shared infrastructure | Collectors base classes, **`core.operations`** (GitHub, markdown, files). Not a “collector” app by itself. |
| **boost_collector_runner** | Scheduling | **`run_scheduled_collectors`** reads YAML; wires Celery Beat. |
| **cppa_user_tracker** | Identity / profiles | Canonical **Identity**, **BaseProfile**, GitHub/Slack/mailing-list profile rows; staging merge tables. |
| **github_activity_tracker** | GitHub mirror | Repos, commits, issues, PRs, **Language** / **License** reference data; workspace JSON cache patterns. |
| **boost_library_tracker** | Boost catalog | **BoostVersion**, **BoostLibrary**, dependencies; GitHub sync helpers (**`run_boost_github_activity_tracker`**, **`collect_boost_libraries`**, etc.). |
| **boost_library_docs_tracker** | Doc scrape + vectors | **`run_boost_library_docs_tracker`**; joins catalog to **BoostDocContent** / Pinecone. |
| **boost_library_usage_dashboard** | Analytics / reporting | **`run_boost_library_usage_dashboard`**; reads aggregated data for dashboards. |
| **boost_usage_tracker** | Repo usage | External repos using Boost; **`run_boost_usage_tracker`**, **`run_update_created_repos_by_language`**, etc. |
| **boost_mailing_list_tracker** | Mailing lists | **`run_boost_mailing_list_tracker`**; raw + formatted workspace layout. |
| **cppa_pinecone_sync** | Vector index | Pinecone upsert / failure tracking; used by doc and GitHub pipelines. |
| **clang_github_tracker** | LLVM/clang mirror | **`run_clang_github_tracker`**; heavy workspace/raw patterns. |
| **cppa_slack_tracker** | Slack messages | **`run_cppa_slack_tracker`**. |
| **discord_activity_tracker** | Discord | **`run_discord_activity_tracker`**, **`run_discord_exporter`**. |
| **wg21_paper_tracker** | WG21 papers | **`run_wg21_paper_tracker`**. |
| **cppa_youtube_script_tracker** | YouTube scripts | **`run_cppa_youtube_script_tracker`**. |
| **slack_event_handler** | Slack events | **`run_slack_event_handler`** (webhook/event path differs from tracker sync). |

**Finding the real command names:** Run `python manage.py help` or list `<app>/management/commands/*.py`. **`config/boost_collector_schedule.yaml`** lists what production *schedules*; names must match actual Django commands (if something fails with “Unknown command”, the YAML or docs may be ahead of or behind the repo).

---

## 4. How data flows between apps (not just tables)

**Schema.md** documents tables and FKs. Onboarding also needs **behavioral** dependencies:

- **Identity chain** — **`cppa_user_tracker`** owns **Identity** / **BaseProfile**. GitHub accounts and other profiles attach here; collectors that attribute activity to people/channels should align with these models (see Schema §1).
- **GitHub hub** — **`github_activity_tracker`** owns **GitHubRepository**, commits, issues, PRs, and shared **Language** / **License**. **`boost_library_tracker`** ties Boost libraries and versions to GitHub data; **`boost_usage_tracker`** consumes repo/language statistics downstream.
- **Workspace-first pipelines** — Apps such as **`github_activity_tracker`** and **`boost_mailing_list_tracker`** use **`workspace/`** as a short-lived JSON cache: persist to DB, then delete files (**[Workspace.md](Workspace.md)**).
- **Pinecone** — **`cppa_pinecone_sync`** and app-specific preprocessors push embeddings; catalog/doc pipelines depend on **`boost_library_tracker`** / **`boost_library_docs_tracker`** rows being current (**[Architecture_data_flow.md](Architecture_data_flow.md)**).

When adding a feature, ask: **who owns the table?** Only that app’s **`services.py`** should write it; other apps **read** via the ORM or call exported service functions if you add them.

---

## 5. Coping with different patterns per app

Historically, collectors evolved separately: some subclass **`CollectorBase`**, some use plain **`BaseCommand`**, workspace layouts differ, and docstring coverage varies. Use this **practical** approach:

1. **Anchor on contracts** — Prefer **`CollectorBase` + `BaseCollectorCommand`** for new work (**[How_to_add_a_collector.md](How_to_add_a_collector.md)**).
2. **Pick two reference apps** — For GitHub + DB + workspace: **`github_activity_tracker`** + **`boost_library_tracker`**. For Pinecone + docs: **`boost_library_docs_tracker`** + **`cppa_pinecone_sync`**.
3. **Trace one vertical slice** — Example: “new Boost release” → **`collect_boost_libraries`** / **`check_new_boost_release`** → downstream **`run_boost_library_docs_tracker`** / usage jobs. Follow imports and **`services`** calls.
4. **Operations vs services** — **`core.operations.github_ops`** = talking to GitHub/git; **`github_activity_tracker.services`** = persisting ORM rows. Do not mix the two responsibilities in one module.

---

## 6. First tasks checklist

- [ ] Clone, venv, **`pip install -r requirements.txt`**, copy **`.env.example`** → **`.env`**, **`migrate`**.
- [ ] Run **`python manage.py help`** and locate commands for the app you care about.
- [ ] Run **pytest** for that app: `python -m pytest <app>/tests` (see README).
- [ ] Read **`services.py`** for that app and the matching **`docs/service_api/<app>.md`** before changing persistence.
- [ ] If you add or rename a scheduled command, update **`config/boost_collector_schedule.yaml`** and **[Workflow.md](Workflow.md)** if behavior/order changes.

---

## 7. Related links

| Topic | Doc |
|-------|-----|
| Add / register a collector | [How_to_add_a_collector.md](How_to_add_a_collector.md) |
| Stable `core` imports | [Core_public_API.md](Core_public_API.md) |
| Full doc index | [README.md](README.md) (this folder) |
