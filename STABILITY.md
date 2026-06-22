# Stability policy

This document defines **which interfaces we treat as stable** for production deployments and in-repo contributors. It complements [Semantic Versioning](https://semver.org/) described in [CHANGELOG.md](CHANGELOG.md).

Boost Data Collector is a **deployed Django application**, not a published PyPI library. Stability commitments apply to **operations** (commands, health checks, configuration) and **documented cross-app Python surfaces**, not to arbitrary imports from tracker apps.

## Audience

| Audience | What this doc covers |
| --- | --- |
| **Operators** | Docker Compose, Celery Beat, migrations, `GET /health/`, environment variables, schedule YAML |
| **Contributors** | `core` public API, `*_sync_api` modules, import-linter boundaries |
| **Out of scope** | Third-party code importing undocumented tracker modules |

## Versioning and branches

- **Version numbers** follow [SemVer](https://semver.org/spec/v2.0.0.html). Release tags (e.g. `v0.1.0`) on **`main`** define production-aligned versions. See [CHANGELOG.md](CHANGELOG.md) for the release checklist and [pyproject.toml](pyproject.toml) (`[tool.setuptools_scm]`) for how `core.__version__` is derived.
- **`0.x` releases:** SemVer treats `0.y.z` as initial development. This policy adds a **practical production contract** for Tier A interfaces below so tagged releases on **`main`** (e.g. `v0.1.0`) are predictable for operators even before `1.0.0`.
- **GitHub default branch** is **`develop`** (where pull requests merge). **Production stability** is defined by **git tags on `main`**, not by every commit on `develop`.
- **Branches:** Deploy production from **`main`** at a **git tag**. **`develop`** is the integration branch; it may change operational behavior until changes are promoted to **`main`**. See [README.md](README.md#branching-strategy) and [SECURITY.md](SECURITY.md#supported-versions) for security-fix flow (`develop` → `main`).
- **Staging:** Pushes to **`develop`** deploy to staging per [docs/Deployment.md](docs/Deployment.md). Staging may run commits not yet on a production tag. **Tier A guarantees apply to tagged `main` releases**; do not assume every `develop` HEAD meets them until promoted and released.
- **We do not backport** stability or feature changes to older tags unless maintainers explicitly agree.

### Release bump rules

| Bump | When | Tier A (stable) interfaces |
| --- | --- | --- |
| **PATCH** (`0.1.x`) | Bug fixes | No intentional breaking changes |
| **MINOR** (`0.2.0`) | Backward-compatible additions | New optional health fields, new schedule tasks, new `sync_api` exports allowed |
| **MAJOR** (`1.0.0`) | Breaking changes to Tier A | Requires CHANGELOG entry and migration notes |

## Interface tiers

### Tier A — Stable

Breaking changes require a **major** release (or an explicit deprecation period documented in CHANGELOG). Pull requests that change these surfaces must update this file and [CHANGELOG.md](CHANGELOG.md) when behavior or names change.

| Interface | Stability commitment | Reference |
| --- | --- | --- |
| **Management commands** in the production schedule | Command names referenced by `config/boost_collector_schedule.yaml` are stable; renaming or removing a scheduled command is breaking | [config/boost_collector_schedule.yaml.example](config/boost_collector_schedule.yaml.example), [docs/Workflow.md](docs/Workflow.md) |
| **Health endpoint** | `GET /health/` response shape and HTTP semantics (see [Health endpoint contract](#health-endpoint-contract)) | [config/health.py](config/health.py) |
| **Environment variables** | Documented names in [`.env.example`](.env.example) are stable on rename (deprecation required); see [minimum operational set](#tier-a-environment-variables-minimum-operational-set) | `.env.example`, [README.md](README.md#critical-environment-variables) |
| **Schedule YAML shape** | Keys and structure in [Schedule YAML (Tier A keys)](#schedule-yaml-tier-a-keys) | [docs/Workflow.md](docs/Workflow.md) |
| **`core` public Python API** | **Entire** [docs/Core_public_API.md](docs/Core_public_API.md) — collectors, `core.errors`, and `core.protocols` | [docs/Core_public_API.md](docs/Core_public_API.md) |
| **Cross-app `sync_api` modules** | Only symbols in each module’s `__all__` | [github_activity_tracker/sync_api.py](github_activity_tracker/sync_api.py), [cppa_pinecone_sync/sync_api.py](cppa_pinecone_sync/sync_api.py); enforced by [`.importlinter`](.importlinter) |

#### Scheduled management commands (example schedule)

**Orchestration (Tier A):**

- **`run_scheduled_collectors`** — runs tasks from `config/boost_collector_schedule.yaml`. Stable CLI flags: `--schedule`, `--group`, `--strict`, `--day-of-week`, `--day-of-month`, `--interval-minutes` (behavior in [docs/Workflow.md](docs/Workflow.md)).
- **`boost_collector_runner.tasks.run_scheduled_collectors_task`** — Celery entry point; stable behavior (delegates to the management command with equivalent kwargs). Operators normally do not invoke this directly.

These per-collector command names appear in [config/boost_collector_schedule.yaml.example](config/boost_collector_schedule.yaml.example). Production `config/boost_collector_schedule.yaml` may add tasks but should not rename scheduled commands without a major release note:

- `run_boost_usage_tracker`
- `run_update_created_repos_by_language`
- `run_boost_github_activity_tracker`
- `run_boost_library_usage_dashboard`
- `run_clang_github_tracker`
- `collect_boost_libraries`
- `run_wg21_paper_tracker`
- `run_cppa_slack_tracker`
- `run_boost_mailing_list_tracker`

Other `manage.py` commands exist for manual runs, backfills, and development; only commands **listed in your deployed schedule YAML** (plus **`run_scheduled_collectors`**) are Tier A for that deployment.

#### Schedule YAML (Tier A keys)

| Level | Stable keys |
| --- | --- |
| Top-level | `groups` |
| Per group | `default_time`, `tasks` |
| Per task | `command`, `schedule` (values: `daily`, `weekly`, `monthly`, `interval`, `on_release`) |
| Per task (optional, Tier A when present) | `enabled` (default: enabled if omitted; `enabled: false` skips the task), `args` (list), `minutes` (interval), `on` / `day_of_week` / `day_of_month` (weekly/monthly) |

New **optional** task keys may be added in minor releases. Changing the meaning of existing keys is breaking.

#### Tier A environment variables (minimum operational set)

[`.env.example`](.env.example) is the authoritative list of documented variable **names**. All documented names follow the rename/deprecation policy below, but not every key is required for every environment.

| Area | Variables |
| --- | --- |
| Core | `DATABASE_URL`, `SECRET_KEY`, `DEBUG`, `WORKSPACE_DIR` |
| Celery | `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` |
| GitHub | `GITHUB_TOKEN`, `GITHUB_TOKENS_SCRAPING`, `GITHUB_TOKEN_WRITE` |
| Health | `HEALTH_CHECK_TOKEN`, `HEALTH_ENFORCE_COLLECTOR_FRESHNESS`, `HEALTH_CELERY_MIN_WORKERS`, `HEALTH_CELERY_INSPECT_TIMEOUT`, `HEALTH_COLLECTOR_STALE_HOURS` |
| Schedule | `BOOST_COLLECTOR_SCHEDULE_YAML`, `BOOST_COLLECTOR_SCHEDULE_STRICT` |

Other variables in `.env.example` remain **name-stable** on rename but may be optional, integration-specific, or dev-only.

**Rename policy:** env var renames need a deprecation note for at least one release (see [Deprecation](#deprecation)).

#### Health endpoint contract

- **URL:** `GET /health/`
- **Success:** HTTP **200** when database and Celery worker checks pass and collector freshness rules pass (see `HEALTH_ENFORCE_COLLECTOR_FRESHNESS` in settings).
- **Failure:** HTTP **503** when critical checks fail.
- **Auth (optional):** If `HEALTH_CHECK_TOKEN` is set, requests must send `Authorization: Bearer <token>`; otherwise HTTP **401** with `{"status": "unauthorized", "detail": "..."}`.
- **Top-level (Tier A):** `status` (`healthy` \| `unhealthy`); `checks` object with keys `database`, `celery_workers`, `collector_groups`, `collector_meta`, `pinecone_sync`. New optional top-level or check keys may be added in minor releases; removing or renaming listed keys is breaking.

##### Health endpoint — nested JSON (Tier A)

| Check key | Stable shape |
| --- | --- |
| `database` | Always `ok` (bool). On success: `latency_ms` (int). On failure: `error` (string). |
| `celery_workers` | `ok`, `workers` (list), `responded`, `expected`; on failure `error`. |
| `collector_groups` | **Dynamic map:** keys are schedule **group ids** (deployment-specific). Per entry: `last_success_at` (ISO 8601 string or null), `stale` (bool or null for groups not on a daily schedule). Key names are **not** fixed across deployments. |
| `collector_meta` | `any_stale`, `enforce_freshness`, `error` (optional), `skipped` (optional string when the database check failed). |
| `pinecone_sync` | **Dynamic map:** keys are `app_type` values from the database; per entry `final_sync_at` (ISO 8601 string or null). The whole object may be `error` or `skipped` when the check failed or was skipped. Key names are **not** fixed across deployments. |

Implementation: [config/health.py](config/health.py).

#### Cross-app `sync_api` exports

**`github_activity_tracker.sync_api`** — `build_issue_document`, `build_pr_document`, `fetcher`, `get_commit_json_path`, `get_issue_json_path`, `get_pr_json_path`, `get_raw_source_issue_path`, `get_raw_source_pr_path`, `iter_existing_commit_jsons`, `iter_existing_issue_jsons`, `iter_existing_pr_jsons`, `normalize_issue_json`, `normalize_pr_json`, `save_commit_raw_source`, `save_issue_raw_source`, `save_pr_raw_source`.

**`cppa_pinecone_sync.sync_api`** — `PineconeInstance`, `PreprocessFn`, `sync_to_pinecone`.

Other tracker apps must not import `fetcher`, `sync`, `ingestion`, `services`, `workspace`, or `preprocessors` directly where [`.importlinter`](.importlinter) forbids it.

#### Cross-app surfaces (summary)

| Surface | Tier | Rule |
| --- | --- | --- |
| `*_sync_api` | **A** | Import only symbols in `__all__` |
| `{app}.services` | **B** | Allowed cross-app reads/writes per [CONTRIBUTING.md](CONTRIBUTING.md); signatures may change in `0.x` minors |
| Tracker internals (`fetcher`, `sync`, ORM outside `services`) | **C** | Forbidden where [`.importlinter`](.importlinter) says so |

See [docs/cross-app-dependencies.md](docs/cross-app-dependencies.md) for the full coupling map.

### Tier B — Evolving

Supported in production with **forward migrations** and **CHANGELOG** notes. Not treated as import-stable across minor releases.

| Interface | Policy |
| --- | --- |
| **PostgreSQL schema** | Changed only via Django migrations; every deploy runs `python manage.py migrate` |
| **`services.py` functions** | Per-app write API; signatures may change in minor `0.x` releases when [docs/service_api/](docs/service_api/) and all callers are updated together. Cross-app reads should use **`services`** or **`sync_api`**, not foreign models (see [CONTRIBUTING.md](CONTRIBUTING.md)) |
| **Collector run outcomes** | `TrackerResult.success` and `errors` must reflect the real outcome (e.g. batch backfills must not report `success=True` when individual files fail). `AbstractCollector.last_result` is the most recent **fully** successful `run()` — after `collect()` **and** `post_collect()` (including checkpoint persistence) complete without error. |

### Tier C — Unstable

No compatibility promise. May change in any release without deprecation.

- Direct `Model.objects` queries or ORM access outside an app’s `services.py` (except intentional identity-hub FKs documented in [docs/cross-app-dependencies.md](docs/cross-app-dependencies.md)).
- Imports of tracker internals bypassing `sync_api` (e.g. `github_activity_tracker.fetcher`, `cppa_pinecone_sync.sync` from apps covered by import-linter).
- Workspace directory layouts under `WORKSPACE_DIR`, except paths explicitly documented in [`.env.example`](.env.example) and [docs/Workspace.md](docs/Workspace.md). **Per-app JSON schemas** under `workspace/` are not stable.
- Docker Compose service names (`web`, `celery_worker`, `celery_beat`) and host ports are not Tier A unless documented here in a future release.
- Optional apps registered via `config/local_settings.py`, management commands not in your schedule, scripts under `scripts/`, tests, and Django admin customization.

## Deprecation

- Prefer **additive** changes in minor releases.
- **Python:** emit `DeprecationWarning`, document in CHANGELOG, and keep the old symbol for at least one release cycle when feasible.
- **Configuration:** document env var renames in CHANGELOG and keep the old name commented in `.env.example` for at least one release cycle when feasible.
- **Breaking removals** of Tier A interfaces target **`1.0.0`**, except urgent security mitigations (see [SECURITY.md](SECURITY.md)).

## How this policy is enforced

This policy is not honor-system only:

- **import-linter** — `lint-imports` (pre-commit and CI) enforces import contracts in [`.importlinter`](.importlinter), implementing Tier C boundaries between tracker apps.
- **`scripts/check_service_layer_writes.py`** — pre-commit and CI; flags ORM writes outside the owning app’s `services.py` (see [CONTRIBUTING.md](CONTRIBUTING.md)).

## Production deployments

1. Build and deploy from **`main`** at a **git tag** (e.g. `v0.1.0`); pin the image or git SHA in production.
2. Run migrations after deploy (`manage.py migrate --noinput`).
3. Verify readiness: `curl -fsS http://<host>/health/` (see [docs/GCP_Production_Checklist.md](docs/GCP_Production_Checklist.md)).
4. Optional: log `core.__version__` for support correlation.
5. Do not assume arbitrary commits on **`develop`** meet Tier A guarantees until they are released on **`main`**.

## Related documentation

- [docs/Core_public_API.md](docs/Core_public_API.md) — stable `core` imports
- [docs/Workflow.md](docs/Workflow.md) — schedule types and `run_scheduled_collectors`
- [docs/cross-app-dependencies.md](docs/cross-app-dependencies.md) — import/FK boundaries
- [docs/Deployment.md](docs/Deployment.md) — staging vs production deploys
- [docs/GCP_Production_Checklist.md](docs/GCP_Production_Checklist.md) — production readiness
- [`.env.example`](.env.example) — authoritative env names (see [minimum operational set](#tier-a-environment-variables-minimum-operational-set))
- [CONTRIBUTING.md](CONTRIBUTING.md) — service layer and contributor rules
- [CHANGELOG.md](CHANGELOG.md) — release notes and semver
- [SECURITY.md](SECURITY.md) — supported versions and vulnerability reporting
