# Contributing to Boost Data Collector

This document describes how to contribute to the project, with emphasis on the **service layer** and data-write rules.

## Creating a new collector

**Start here:** [docs/Tutorial_building_a_collector.md](docs/Tutorial_building_a_collector.md) — step-by-step walkthrough (scaffolding, `AbstractCollector` hooks, testing, YAML/Celery, deployment) with a worked `heartbeat_demo` example.

Use the **`startcollector`** management command to generate a new Django app with the usual collector layout (stub `models.py`, `services.py`, `AbstractCollector` + `BaseCollectorCommand`, `tests/` package, `migrations/0001_initial.py`, and `schedule_snippet.yaml`). Run it from the **repository root** so the new package sits next to the other apps.

```bash
# Preview only (no files written)
python manage.py startcollector my_platform --dry-run

# Create ./my_platform/ (pick a unique snake_case name)
python manage.py startcollector my_platform
```

**What you get**

- App package `my_platform/` with `apps.py` (`BigAutoField`, correct `name`), `models.py` (stub run-state model), `services.py` (stub `record_run` — all writes for this app should stay in this module per [Service layer](#service-layer-single-place-for-writes) below).
- `management/commands/run_my_platform.py` — collector subclasses **`AbstractCollector`**; command subclasses **`BaseCollectorCommand`**.
- `tests/test_run_my_platform_command.py` — smoke test; it runs only after you register the app (next step).
- `schedule_snippet.yaml` — commented template to paste into **`config/boost_collector_schedule.yaml`** (see [Workflow.md](docs/Workflow.md)).

**What you must do manually**

1. Add **`"my_platform"`** to **`INSTALLED_APPS`** in `config/settings.py` (keep alphabetical order with the other project apps).
2. Merge the task from `schedule_snippet.yaml` into **`config/boost_collector_schedule.yaml`** under the right `groups.<name>.tasks` entry (see [Workflow.md](docs/Workflow.md)).
3. Run **`python manage.py migrate`** so the new tables exist.
4. When the app imports other apps or defines cross-app foreign keys, update **[cross-app-dependencies.md](docs/cross-app-dependencies.md)** (add or adjust the row for your app).
5. As `services.py` grows, run **`python scripts/generate_service_docs.py`** and commit the generated `docs/service_api/` updates when you add public service functions.

**Docs and contracts**

- Collector lifecycle, errors, and optional `sync_pinecone`: [How_to_add_a_collector.md](docs/How_to_add_a_collector.md) and [Core_public_API.md](docs/Core_public_API.md).
- **CI:** The **pyright** workflow runs **`python scripts/validate_collector_scaffold.py`**, which recreates a throwaway app under `.test_artifacts/`, then runs **ruff** and a **scoped pyright** check on that tree.

## Service layer: single place for writes

Each Django app that has **models** provides a **`services.py`** module. This is the **only** place where code should create, update, or delete rows for that app’s models.

### Rule

- **All** inserts/updates/deletes for an app’s models must go through functions in that app’s **`services.py`**.
- Do **not** call `Model.objects.create()`, `model.save()`, or `model.delete()` from outside `services.py` (e.g. from management commands, views, other apps, or tests that are not testing the service layer itself).

**CI:** Pre-commit runs **`uv run python scripts/check_service_layer_writes.py`**, which flags ORM writes outside the owning app’s `services.py` (see [docs/cross-app-dependencies.md](docs/cross-app-dependencies.md) §6). Temporary grandfathering uses [`.service-layer-write-allowlist.json`](.service-layer-write-allowlist.json) plus a `# TODO(service-layer):` comment; do not add new allowlist rows without maintainer agreement—fix the code or extend the correct `services.py` instead.

### Why

- **Single place for write logic:** Validation, defaults, and side effects live in one module.
- **Easier to change:** Schema or business rules can be updated in one place.
- **Clear API:** Contributors know where to look and what to call.

### Which apps have a service layer

| App                       | File                                  | Notes                                         |
| ------------------------- | ------------------------------------- | --------------------------------------------- |
| `boost_collector_runner`  | `boost_collector_runner/services.py`  | Collector group run status (YAML schedule groups). |
| `cppa_user_tracker`       | `cppa_user_tracker/services.py`       | Identity, profiles, emails, staging.     |
| `github_activity_tracker` | `github_activity_tracker/services.py` | Repos, languages, licenses, issues, PRs. |
| `boost_library_tracker`   | `boost_library_tracker/services.py`   | Boost libraries, versions, dependencies, categories, roles. |
| `boost_library_docs_tracker` | `boost_library_docs_tracker/services.py` | BoostDocContent and BoostLibraryDocumentation (doc scrape and sync status). |
| `boost_usage_tracker`     | `boost_usage_tracker/services.py`     | External repos, Boost usage, missing-header tmp. |
| `cppa_pinecone_sync`       | `cppa_pinecone_sync/services.py`       | Pinecone fail list and sync status writes.                  |
| `discord_activity_tracker` | `discord_activity_tracker/services.py` | Servers, channels, messages, reactions (Discord user profiles in cppa_user_tracker). |
| `cppa_youtube_script_tracker` | `cppa_youtube_script_tracker/services.py` | YouTube channels, videos, tags, transcript state, speaker links. |
| `clang_github_tracker` | `clang_github_tracker/services.py` | Clang/llvm GitHub issue, PR, and commit upserts; fetch watermarks. |
| `boost_mailing_list_tracker` | `boost_mailing_list_tracker/services.py` | Mailing list messages and names. |
| `cppa_slack_tracker` | `cppa_slack_tracker/services.py` | Slack teams, channels, messages, membership. |
| `reddit_activity_tracker` | `reddit_activity_tracker/services.py` | Reddit submissions and comments. |
| `wg21_paper_tracker` | `wg21_paper_tracker/services.py` | WG21 papers, authors, mailings. |

For a full list of functions, parameter/return types, and validation (e.g. empty `name` raises `ValueError`), see **[docs/Service_API.md](docs/Service_API.md)** and the per-app docs in **[docs/service_api/](docs/service_api/)** (index: [docs/service_api/README.md](docs/service_api/README.md)). DTO protocols shared across trackers are documented in **[docs/service_api/core_protocols.md](docs/service_api/core_protocols.md)** (generated from `core/protocols.py`).

### Regenerating service API docs

Reference tables in `docs/service_api/*.md` are produced by **[`scripts/generate_service_docs.py`](scripts/generate_service_docs.py)** from each app’s `services.py` and from `core/protocols.py`.

- **Markers:** Each file contains `<!-- SERVICE_API:GENERATED:START -->` … `<!-- SERVICE_API:GENERATED:END -->`. The script replaces **only** that region. Put hand-written notes (usage, cross-app warnings, command help) **below** the `END` marker.
- **Regenerate locally:** `python scripts/generate_service_docs.py` (optional: `--app <django_app_label>` for one module).
- **Check only:** `python scripts/generate_service_docs.py --check` exits non-zero if committed markdown would change.
- **CI / pre-commit:** The **lint** job runs pre-commit, which includes this check. Pull requests that change **only** ignored paths (`**.md`, `docs/**` per `.github/workflows/actions.yml`) do not run CI; any PR that touches `**/services.py` or `core/protocols.py` still runs the check—regenerate docs before pushing.

### How to use

1. **From management commands or other apps:** Import and call the service functions.

   ```python
   from cppa_user_tracker.services import create_identity, add_email
   from github_activity_tracker.services import get_or_create_language, add_pull_request_label

   identity = create_identity(display_name="Jane")
   add_email(identity.profiles.first(), "jane@example.com")
   lang, _ = get_or_create_language("Python")
   add_pull_request_label(pr, "bug")
   ```

2. **Adding new write behavior:** Add a new function in the app’s `services.py` (and optionally a helper in the same module). Do not add new writes by calling the model or manager directly from outside `services.py`.

3. **Reading data:** No restriction. Use the ORM as usual: `Model.objects.filter(...)`, `model.related_set.all()`, etc.

### Testing

- **Running tests:** From the project root, install dev deps (`pip install -r requirements-dev.lock` or `uv pip install -r requirements-dev.lock`), start the test database (`docker compose -f docker-compose.test.yml up -d`), set `DATABASE_URL` (and `SECRET_KEY` for the process) as in [README.md](README.md#running-tests), then run `python -m pytest`. Tests **always use PostgreSQL** (`config.test_settings`); there is no SQLite fallback.
- **`boost_library_docs_tracker` / pandoc:** If you work on the docs collector or run tests that hit real HTML→Markdown conversion, install the **`pandoc`** system binary per [README — System dependencies](README.md#system-dependencies) (`pypandoc` from pip is not enough).
- See [README.md](README.md#running-tests) and [docs/Development_guideline.md](docs/Development_guideline.md#testing-workflow) for full commands and options.
- **Unit tests for `services.py`:** Call the service functions and assert on the database (or mocks) as needed.
- **Other tests:** Prefer service functions when setting up data. If you must create models directly for tests, keep it in test code (e.g. fixtures or test helpers) and avoid doing the same in production code.

### Performance benchmarks

Throughput checks live under [`benchmarks/`](benchmarks/) and use **`pytest-benchmark`**. They are **not** collected during normal `pytest` runs: set **`RUN_BENCHMARKS=1`** so the root [`conftest.py`](conftest.py) stops ignoring that directory (see `collect_ignore`). Tests are marked with **`@pytest.mark.benchmark`**.

**Prerequisites:** Same as unit tests: PostgreSQL, `DATABASE_URL`, `SECRET_KEY`, `DJANGO_SETTINGS_MODULE=config.test_settings` (see [README.md](README.md#running-tests)).

**Run locally** (from repo root, with Postgres up):

```bash
export RUN_BENCHMARKS=1
export DATABASE_URL=postgres://postgres:postgres@127.0.0.1:5433/postgres
export SECRET_KEY=for-local-only
export DJANGO_SETTINGS_MODULE=config.test_settings
# Optional: batch size (default 50; match benchmarks/baselines.json "n")
export BENCHMARK_COMMIT_N=50

uv run pytest benchmarks/ -m benchmark --benchmark-only \
  --benchmark-json=bench.json -v \
  --benchmark-disable-gc \
  --benchmark-min-rounds=5 \
  --benchmark-warmup=on
uv run python benchmarks/compare_to_baseline.py bench.json benchmarks/baselines.json
```

**Baselines:** [`benchmarks/baselines.json`](benchmarks/baselines.json) stores maximum acceptable **median** seconds per scenario (for the configured `n`). The compare script fails if any median exceeds `baseline_median × 1.10` (more than 10% slower than the reference). Override with `--regression-ratio` or `BENCHMARK_REGRESSION_RATIO`. After a deliberate performance change or a CI image upgrade, update `median_seconds` (and `n` if you change `BENCHMARK_COMMIT_N`) using `stats.median` from the generated JSON.

**Updating baselines (deliberate, not automatic):**

1. Run benchmarks locally, or trigger [`.github/workflows/benchmarks.yml`](.github/workflows/benchmarks.yml) via **workflow_dispatch** with **skip regression check** enabled.
2. Download the `benchmark-json-<run_id>` artifact (or use local `bench.json`).
3. Copy each scenario's `stats.median` into `benchmarks/baselines.json` and keep `"n"` in sync with `BENCHMARK_COMMIT_N`.
4. Open a PR that changes only `baselines.json`, with a short note explaining why (perf improvement, CI runner change, etc.).

**CI:** [`.github/workflows/benchmarks.yml`](.github/workflows/benchmarks.yml) runs on **push** and **pull requests** targeting **`main`** and **`develop`** (doc-only changes are skipped via `paths-ignore`, same as the main CI workflow). It uploads `bench.json` as an artifact, compares medians against the checked-in baselines at the 10% threshold, and also supports **workflow_dispatch** for manual runs and baseline calibration. During initial rollout the `benchmark` job is **informational** (not a required branch-protection check); see [docs/CODEOWNERS_and_branch_protection.md](docs/CODEOWNERS_and_branch_protection.md).

## Dependency security audit

Every pull request runs **[`.github/workflows/security-audit.yml`](.github/workflows/security-audit.yml)** (`pip-audit` against the pinned dependency trees). Unlike the main [CI workflow](.github/workflows/actions.yml), this workflow has **no `paths-ignore`**, so doc-only PRs still get a dependency scan.

**What is scanned**

- [`requirements.lock`](requirements.lock) — production / Docker image
- [`requirements-dev.lock`](requirements-dev.lock) — dev and CI (includes `-r requirements.in`)

**Run locally** (same command as CI, from the repo root):

```bash
uv venv
uv pip install "pip-audit>=2.10,<3"
uv run pip-audit --desc on -r requirements.lock -r requirements-dev.lock
```

If the audit reports a vulnerable package, bump the constraint in [`requirements.in`](requirements.in) or [`requirements-dev.in`](requirements-dev.in), then regenerate locks:

```bash
uv pip compile requirements.in -o requirements.lock --python-version 3.13 --python-platform linux
uv pip compile requirements-dev.in -o requirements-dev.lock --python-version 3.13 --python-platform linux
```

Commit the updated `.in` and `.lock` files. Prefer fixing versions over long-lived `--ignore-vuln` entries.

## Other guidelines

- **Branching:** Create feature branches from `develop`. Open pull requests against `develop`. See [docs/Development_guideline.md](docs/Development_guideline.md).
- **Code style:** Use Python 3.13 and follow Django and project conventions. Use the project’s logging (`logging.getLogger(__name__)`). Before pushing, run **`uv run pyright`** (with dev deps) for the paths covered by **`pyrightconfig.json`**, and ensure CI’s **lint** / **pyright** / **test-ubuntu** / **test-macos** / **test-windows** / **Security audit** jobs would pass.
- **Database:** Use the Django ORM and migrations. Writes only through the service layer as above.
- **Docs:** Update this file (and app `services.py` docstrings) when adding new apps or changing the write rules. After changing `services.py` or `core/protocols.py`, run `python scripts/generate_service_docs.py` and commit the updated `docs/service_api/` files.
- **Stability:** Pull requests that change `sync_api.__all__`, the `/health/` JSON contract, or management command names used in `config/boost_collector_schedule.yaml` must update [STABILITY.md](STABILITY.md) and [CHANGELOG.md](CHANGELOG.md) when the change is user-visible.

## Related documentation

- [docs/Service_API.md](docs/Service_API.md) – API reference for all service layer functions.
- [docs/Development_guideline.md](docs/Development_guideline.md) – Setup, workflow, adding apps.
- [docs/Workflow.md](docs/Workflow.md) – Execution order and collectors.
- [docs/Schema.md](docs/Schema.md) – Database schema.
- [docs/cross-app-dependencies.md](docs/cross-app-dependencies.md) – Complete map of every cross-app FK, MTI, ORM read, and Python import dependency, plus `import-linter` recommendations.
