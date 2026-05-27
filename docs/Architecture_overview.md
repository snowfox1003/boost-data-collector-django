# Architecture overview

**Start here for system design.** This page is the single entry point for all Django apps in Boost Data Collector: what each package does, where data lives, how apps depend on each other, and where to read next.

**Last verified:** 2026-05-26 (against `develop`).

For diagrams and ingest flow, see [Architecture_data_flow.md](Architecture_data_flow.md). For FK/import detail, see [cross-app-dependencies.md](cross-app-dependencies.md). For first-day setup, see [Onboarding.md](Onboarding.md).

---

## 1. Purpose and scope

- **One Django project**, **one PostgreSQL database** (`boost_dashboard`); all project apps share `config/settings.py`.
- **Collectors** are `management/commands` (e.g. `run_boost_mailing_list_tracker`). Production batches use **`boost_collector_runner`** → **`run_scheduled_collectors`** reading [`config/boost_collector_schedule.yaml`](../config/boost_collector_schedule.yaml) (see [Workflow.md](Workflow.md)).
- **Writes** to an app’s models go only through that app’s **`services.py`** ([CONTRIBUTING.md](../CONTRIBUTING.md)).
- **Cross-app imports** are constrained by **import-linter** (see [cross-app-dependencies.md §5](cross-app-dependencies.md#5-import-linting--import-linter-enabled)).

The ticket term **“15 Django apps”** means all **domain/orchestration** packages below **except `core`** (shared library). This doc covers **16** rows: **15** domain apps + **`core`**.

---

## 2. Platform layer

| Package | Role | Models / services | Deep dive |
|---------|------|-------------------|-----------|
| **`core`** | Collector contracts (`AbstractCollector`, `BaseCollectorCommand`), structured errors, **`core.operations`** (GitHub, Slack, files, markdown) | No ORM; not a data domain | [core/README.md](../core/README.md), [Core_public_API.md](Core_public_API.md) |
| **`boost_collector_runner`** | Resolves YAML schedule; runs `run_scheduled_collectors` | `services.py` for group run status only | [boost_collector_runner/README.md](../boost_collector_runner/README.md), [Workflow.md](Workflow.md) |

---

## 3. Master app reference (15 domain apps + platform)

Columns: **persistence** (usual durable stores), **coupling** (one-line upstream → downstream), **docs** (app README, service API, schema).

| App | Role | Models / `services.py` | Persistence | Coupling (summary) | Docs |
|-----|------|------------------------|-------------|-------------------|------|
| **`core`** | Shared collector + operations library | No models | N/A | Used by all collectors | [README](../core/README.md), [Core_public_API](Core_public_API.md) |
| **`boost_collector_runner`** | YAML / Celery orchestration | Run status only | N/A | Invokes all `run_*` commands | [README](../boost_collector_runner/README.md), [service_api](service_api/boost_collector_runner.md) |
| **`cppa_user_tracker`** | Identity hub (GitHub, Slack, Discord, WG21, mailing list, YouTube profiles) | Yes | PostgreSQL | **Upstream:** none (hub). **Downstream:** all person-attributed trackers | [README](../cppa_user_tracker/README.md), [service_api](service_api/cppa_user_tracker.md), [Schema § Overview](Schema.md#overview) |
| **`github_activity_tracker`** | GitHub repos, commits, issues, PRs; Language/License reference | Yes | PostgreSQL, workspace | **Upstream:** `cppa_user_tracker`. **Downstream:** Boost, usage, clang pipelines | [README](../github_activity_tracker/README.md), [service_api](service_api/github_activity_tracker.md) |
| **`boost_library_tracker`** | Boost catalog, versions, dependencies, maintainer roles | Yes | PostgreSQL, workspace | **Upstream:** `github_activity_tracker`, `cppa_user_tracker`. **Downstream:** docs, usage | [README](../boost_library_tracker/README.md), [service_api](service_api/boost_library_tracker.md) |
| **`boost_library_docs_tracker`** | Boost documentation crawl and doc rows | Yes | PostgreSQL, workspace | **Upstream:** `boost_library_tracker`. **Downstream:** `cppa_pinecone_sync` | [README](../boost_library_docs_tracker/README.md), [service_api](service_api/boost_library_docs_tracker.md) |
| **`boost_library_usage_dashboard`** | Dashboard / aggregation (**shim** — no local domain models) | Reads peers; no generated service_api | PostgreSQL, workspace exports | **Upstream:** `boost_usage_tracker`, others. **Downstream:** reporting only | [README](../boost_library_usage_dashboard/README.md) — *no [service_api](service_api/) page* |
| **`boost_usage_tracker`** | External repos using Boost headers | Yes | PostgreSQL, workspace | **Upstream:** `github_activity_tracker`, `boost_library_tracker`. **Downstream:** dashboard | [README](../boost_usage_tracker/README.md), [service_api](service_api/boost_usage_tracker.md) |
| **`boost_mailing_list_tracker`** | Mailing list archives | Yes | PostgreSQL, workspace | **Upstream:** `cppa_user_tracker`. **Downstream:** optional Pinecone | [README](../boost_mailing_list_tracker/README.md), [service_api](service_api/boost_mailing_list_tracker.md) |
| **`cppa_pinecone_sync`** | Vector upserts, fail lists, sync status | Yes | PostgreSQL, Pinecone | **Upstream:** doc/GitHub/mailing collectors. **Downstream:** Pinecone index | [README](../cppa_pinecone_sync/README.md), [service_api](service_api/cppa_pinecone_sync.md), [Pinecone_preprocess_guideline](Pinecone_preprocess_guideline.md) |
| **`clang_github_tracker`** | LLVM/Clang GitHub activity | Yes | PostgreSQL, workspace | **Upstream:** `github_activity_tracker` (via `sync_api`), `cppa_user_tracker` | [README](../clang_github_tracker/README.md), [service_api](service_api/clang_github_tracker.md) |
| **`cppa_slack_tracker`** | Slack teams, channels, messages | Yes | PostgreSQL, workspace | **Upstream:** `cppa_user_tracker` | [README](../cppa_slack_tracker/README.md), [service_api](service_api/cppa_slack_tracker.md) |
| **`discord_activity_tracker`** | Discord servers, channels, messages | Yes | PostgreSQL, workspace | **Upstream:** `cppa_user_tracker` | [README](../discord_activity_tracker/README.md), [service_api](service_api/discord_activity_tracker.md) |
| **`wg21_paper_tracker`** | WG21 papers and authors | Yes | PostgreSQL, workspace | **Upstream:** `cppa_user_tracker` | [README](../wg21_paper_tracker/README.md), [service_api](service_api/wg21_paper_tracker.md) |
| **`cppa_youtube_script_tracker`** | YouTube metadata and transcripts | Yes | PostgreSQL, workspace | **Upstream:** `cppa_user_tracker` | [README](../cppa_youtube_script_tracker/README.md), [service_api](service_api/cppa_youtube_script_tracker.md) |
| **`slack_event_handler`** | Slack Socket Mode listener (PR bot / huddles) — **long-running**, not YAML batch | **No ORM** / no `services.py` | Workspace JSON, GitHub optional | **Upstream:** Slack events. **Downstream:** GitHub MD via operations | [README](../slack_event_handler/README.md) — *no [service_api](service_api/) page* |

**Primary scheduled commands** (YAML / Celery batch via `config/boost_collector_schedule.yaml`; non-exhaustive — see [Workflow.md](Workflow.md)):

| App | Typical `run_*` command |
|-----|-------------------------|
| `boost_collector_runner` | `run_scheduled_collectors` |
| `cppa_user_tracker` | `run_cppa_user_tracker` |
| `github_activity_tracker` | (via `boost_library_tracker`) `run_boost_github_activity_tracker` |
| `boost_library_tracker` | `run_boost_github_activity_tracker`, `collect_boost_libraries`, … |
| `boost_library_docs_tracker` | `run_boost_library_docs_tracker` |
| `boost_library_usage_dashboard` | `run_boost_library_usage_dashboard` |
| `boost_usage_tracker` | `run_boost_usage_tracker`, `run_update_created_repos_by_language`, … |
| `boost_mailing_list_tracker` | `run_boost_mailing_list_tracker` |
| `cppa_pinecone_sync` | `run_cppa_pinecone_sync` |
| `clang_github_tracker` | `run_clang_github_tracker` |
| `cppa_slack_tracker` | `run_cppa_slack_tracker` |
| `discord_activity_tracker` | `run_discord_activity_tracker` |
| `wg21_paper_tracker` | `run_wg21_paper_tracker` |
| `cppa_youtube_script_tracker` | `run_cppa_youtube_script_tracker` |

**Long-running entrypoint services** (not in the YAML schedule; run as a persistent process, e.g. Compose / `runserver` integration):

| App | Entry command | Notes |
|-----|---------------|-------|
| `slack_event_handler` | `run_slack_event_handler` | Slack Socket Mode listener (PR bot / huddles); see [Docker.md §4b](Docker.md#4b-slack-session-tokens-huddle-transcripts-optional) |

---

## 4. Vertical slices

### Identity hub

`cppa_user_tracker` owns **Identity** and profile tables. Trackers that attribute activity to people hold FKs into this app (intentional hub — see [cross-app-dependencies.md §1](cross-app-dependencies.md#1-schema-coupling-orm--fk-and-mti-in-modelspy)).

### GitHub / Boost chain

1. `github_activity_tracker` — raw GitHub mirror and reference data.
2. `boost_library_tracker` — catalog tied to GitHub repos/files (MTI/OneToOne into github models).
3. `boost_library_docs_tracker` — documentation rows keyed to library versions.
4. `boost_usage_tracker` / `boost_library_usage_dashboard` — usage and reporting downstream.

### Pinecone pipeline

Collectors persist to PostgreSQL and/or workspace → **`cppa_pinecone_sync`** (and some in-command sync phases) upsert embeddings. Namespace and field rules: [Pinecone_preprocess_guideline.md](Pinecone_preprocess_guideline.md).

---

## 5. Boundaries and coupling

- **Service layer:** All creates/updates/deletes for an app’s models go through that app’s `services.py`. Index: [Service_API.md](Service_API.md), [service_api/README.md](service_api/README.md).
- **Schema vs behavior:** Table diagrams in [Schema.md](Schema.md); import/FK matrix in [cross-app-dependencies.md](cross-app-dependencies.md).
- **Import linting:** Run `lint-imports` locally; config in [`.importlinter`](../.importlinter). Regenerate import tables: `python scripts/list_cross_app_imports.py`.

---

## 6. Extension points

- **New collector app:** `python manage.py startcollector <app_label>` — see [CONTRIBUTING.md § Creating a new collector](../CONTRIBUTING.md#creating-a-new-collector) and [How_to_add_a_collector.md](How_to_add_a_collector.md).
- **Schedule:** Add tasks to `config/boost_collector_schedule.yaml` ([Workflow.md](Workflow.md)).
- **New cross-app coupling:** Update [cross-app-dependencies.md](cross-app-dependencies.md) and ensure import-linter contracts still pass.

---

## 7. Diagrams

High-level data movement (sources → collectors → DB / workspace → Pinecone) and orchestration:

- [Architecture_data_flow.md §1–2](Architecture_data_flow.md) — Mermaid flowcharts and per-app persistence table.

---

## Related

| Topic | Doc |
|-------|-----|
| Onboarding / mental model | [Onboarding.md](Onboarding.md) |
| PR reviews / CODEOWNERS | [CODEOWNERS_and_branch_protection.md](CODEOWNERS_and_branch_protection.md) |
| 1:1 walkthrough runbooks | [onboarding/](onboarding/README.md) |
| Bus-factor ticket checklist | [BUS_FACTOR_DELIVERABLES.md](BUS_FACTOR_DELIVERABLES.md) |
