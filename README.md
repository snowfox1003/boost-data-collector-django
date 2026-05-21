# Boost Data Collector - Django project

## Overview

Boost Data Collector is a Django project that collects and manages data from various Boost-related sources. The project has multiple Django apps in one repository. All apps share one virtual environment, one database (PostgreSQL), and the same Django settings. Each app exposes one or more management commands (e.g. `python manage.py run_boost_github_activity_tracker`). Production scheduling uses **Celery Beat** and **`config/boost_collector_schedule.yaml`** (start from [`config/boost_collector_schedule.yaml.example`](config/boost_collector_schedule.yaml.example)) via **`run_scheduled_collectors`** (see [docs/Workflow.md](docs/Workflow.md)).

## Security

**Responsible disclosure:** do not open a public GitHub Issue for undisclosed security problems. Read **[`SECURITY.md`](SECURITY.md)** for supported versions, in-scope components, how to report privately (**GitHub Security**; email only when an address is published there), response timelines, and **credential rotation** guidance (GitHub tokens, Slack, Discord, Pinecone, YouTube, browser session material, Django `SECRET_KEY`, database URLs).

## Critical environment variables

Authoritative names, examples, and comments live in **[`.env.example`](.env.example)**. Typical values you must set for a working local or deployed stack:

| Variable | Role |
| --- | --- |
| `DATABASE_URL` | PostgreSQL for Django and for **pytest** (see [Running tests](#running-tests)). |
| `SECRET_KEY` | Django cryptographic signing (required in production; tests often use a disposable value). |
| `GITHUB_TOKEN` / `GITHUB_TOKENS_SCRAPING` / `GITHUB_TOKEN_WRITE` | GitHub API access patterns (details in [GitHub tokens](#github-tokens) and `docs/operations/github.md`). |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | Redis endpoints for Celery worker and Beat (defaults in `.env.example`). |
| `WORKSPACE_DIR` | Optional override for the on-disk **workspace** root used by collectors (see [Workspace](#workspace-rawprocessed-files)). |

## Quick start

### Prerequisites

- Python 3.11+
- Django (version in `requirements.txt`)
- PostgreSQL database access
- **pandoc** — required by `boost_library_docs_tracker` for HTML→Markdown conversion (`pypandoc` calls the `pandoc` binary at runtime):
  - macOS: `brew install pandoc`
  - Debian/Ubuntu: `sudo apt-get install pandoc`
  - Windows: `winget install JohnMacFarlane.Pandoc` or download from [pandoc.org](https://pandoc.org/installing.html)
- Environment variables for database URL and API keys (e.g. via `.env`)

### Initial setup

1. Clone the repository:

```bash
git clone <boost-data-collector-repo-url>
cd boost-data-collector
```

2. Create and activate a virtual environment:

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/macOS
source venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Configure environment variables (e.g. copy `.env.example` to `.env` and set database URL and API credentials).

5. Create and run migrations (required before any command that uses the database):

```bash
python manage.py makemigrations
python manage.py migrate
```

Each project app has a `migrations/` package; if you previously saw "No changes detected" but `migrate` only listed `admin, auth, contenttypes, sessions`, ensure those packages exist and run the commands again. After a successful `migrate` you should see migrations for `cppa_user_tracker`, `github_activity_tracker`, `boost_library_tracker`, `core`, and other installed apps (GitHub utilities under `core.operations.github_ops` are not Django apps and have no migrations).

If you see `relation "cppa_user_tracker_githubaccount" does not exist` (or similar), the database tables are missing — run the two commands above.

6. Run a single app command or the full workflow to confirm the project works:

```bash
python manage.py run_scheduled_collectors --schedule daily --group github
```

7. To **add a new collector app** (boilerplate, management command, and schedule snippet template), use **`python manage.py startcollector <name>`** and follow **[CONTRIBUTING.md](CONTRIBUTING.md#creating-a-new-collector)**.

For local development you can start the dev server: `python manage.py runserver`.

## Running with Docker

You can run the whole stack (Django, PostgreSQL, Redis, Celery worker and beat) in Docker. See **[docs/Docker.md](docs/Docker.md)** for step-by-step instructions, including first-time setup and useful commands.

## Celery

The daily workflow runs as a Celery task (see [docs/Celery_test.md](docs/Celery_test.md)). You need **Redis** running (default: `localhost:6379`). Start the worker and (optionally) Beat in separate terminals:

```bash
# Worker (executes tasks)
celery -A config worker -l info

# Beat (schedules YAML-driven tasks per group / interval)
celery -A config beat -l info
```

On Windows, the project configures the worker to use the `solo` pool automatically; if you see `PermissionError [WinError 5]`, run: `celery -A config worker -l info --pool=solo`.

**Schedule YAML in production:** with `DEBUG=False` (or `BOOST_COLLECTOR_SCHEDULE_STRICT=True`), Django fails to start if `config/boost_collector_schedule.yaml` is missing or invalid, so Celery Beat cannot run with an empty schedule. Use `python manage.py run_scheduled_collectors ... --strict` for a one-off check even when `DEBUG` is True. Startup logs include a short summary of the loaded schedule (see [docs/Workflow.md](docs/Workflow.md)).

## Running tests

The project uses **pytest** with **pytest-django**. Tests run against **`config.test_settings`**, which **always uses PostgreSQL** (same engine as CI and production). **`DATABASE_URL` must be set** when you run pytest; if it is missing, Django raises a clear error (see [`config/test_settings.py`](config/test_settings.py)).

**Why not SQLite:** the ORM behaves differently on SQLite versus PostgreSQL (for example JSONB, `ILIKE` case rules, types such as arrays, and transaction isolation). Using Postgres for tests catches those issues before CI or production.

1. Install test dependencies (once):

```bash
pip install -r requirements-dev.txt
```

2. Start a local PostgreSQL 16 instance for tests (recommended; uses host port **5433** so it does not clash with Postgres on **5432**):

```bash
docker compose -f docker-compose.test.yml up -d
```

3. Set **`DATABASE_URL`** and a dummy **`SECRET_KEY`** for the test process (CI sets these for pytest):

```bash
# Linux / macOS (Git Bash / WSL)
export DATABASE_URL=postgres://postgres:postgres@127.0.0.1:5433/postgres
export SECRET_KEY=for-testing-only
```

```bash
# Windows (Command Prompt)
set DATABASE_URL=postgres://postgres:postgres@127.0.0.1:5433/postgres
set SECRET_KEY=for-testing-only
```

If you already run PostgreSQL yourself, you may point `DATABASE_URL` at that server instead; the user in the URL must be allowed to **create databases** (pytest-django creates a separate database named `test_<dbname>` with `--reuse-db` from [`pytest.ini`](pytest.ini)).

4. Run the full test suite:

```bash
python -m pytest
```

5. Optional: run with coverage and enforce a minimum percentage locally:

```bash
python -m pytest --tb=short --cov=. --cov-report=term-missing --cov-fail-under=90
```

Coverage writes a local **`.coverage`** file (binary data used by `coverage.py`; safe to delete). It is listed in `.gitignore`.

**CI:** [`.github/workflows/actions.yml`](.github/workflows/actions.yml) runs three jobs on pushes/PRs (see the workflow for triggers): **`lint`** (pre-commit on all files), **`pyright`** (static analysis from `pyrightconfig.json`), and **`test`** (pytest with Postgres, `DATABASE_URL=postgres://postgres:postgres@127.0.0.1:5432/postgres`, `DJANGO_SETTINGS_MODULE=config.test_settings`, coverage, and `--cov-fail-under=90`).

6. Run a subset of tests (e.g. one app or one file):

```bash
python -m pytest cppa_user_tracker/tests/ -v
python -m pytest github_activity_tracker/tests/test_sync_utils.py -v
```

CI runs pytest with coverage (`--cov`, HTML/XML reports). To match a **local** coverage gate, use **`--cov-fail-under=90`** (see step 5 above). If coverage fails locally or you need a fresh test DB schema after model changes, run once with `python -m pytest --create-db`.

**Pyright (local):** with dev dependencies installed (`uv pip install -r requirements-dev.lock`), run **`uv run pyright`** from the repo root to match the **`pyright`** CI job (`pyrightconfig.json` scopes `core`, `github_activity_tracker`, and `discord_activity_tracker`).

See [docs/Development_guideline.md](docs/Development_guideline.md#testing-workflow) for when to run tests during development.

## Project structure

Typical top-level layout after clone (folder name is usually **`boost-data-collector-django`**; paths below are relative to that root):

```
.
├── manage.py
├── pyproject.toml
├── pytest.ini
├── Makefile
├── README.md
├── LICENSE
├── CHANGELOG.md
├── conftest.py
├── requirements.txt
├── requirements.lock
├── requirements.in
├── requirements-dev.txt
├── requirements-dev.lock
├── requirements-dev.in
├── .env.example
├── docker-compose.yml
├── docker-compose.ci.yml
├── docker-compose.test.yml
├── Dockerfile
├── docker-entrypoint.sh
├── config/                      # Django project: settings, URLs, Celery, boost_collector_schedule.yaml
├── docs/                        # Design docs, Schema, Workflow, service_api/, operations/, …
├── workspace/                   # Per-app trees + shared areas (see docs/Workspace.md)
│   ├── raw/
│   ├── shared/
│   ├── scripts/
│   ├── github_activity_tracker/
│   └── …                        # e.g. boost_library_tracker/, discord_activity_tracker/, …
├── scripts/                     # Repo maintenance and codegen helpers
├── core/                        # Shared collectors + operations (GitHub, Slack, markdown, files)
├── boost_collector_runner/      # YAML schedule → run_scheduled_collectors
├── boost_library_docs_tracker/
├── boost_library_tracker/
├── boost_library_usage_dashboard/
├── boost_mailing_list_tracker/
├── boost_usage_tracker/
├── clang_github_tracker/
├── cppa_pinecone_sync/
├── cppa_slack_tracker/
├── cppa_user_tracker/
├── cppa_youtube_script_tracker/
├── discord_activity_tracker/
├── github_activity_tracker/
├── slack_event_handler/
└── wg21_paper_tracker/
```

Each Django app can expose management commands in `management/commands/`. All apps are in `INSTALLED_APPS` and use the shared database.

## App-level READMEs

Some Django apps include a **README.md** at the app package root when that helps readers: **non-obvious behavior**, **operations** (Celery, schedule YAML), **dense management commands**, or **shared infrastructure**. The **`config/`** package has no README here—use [`config/settings.py`](config/settings.py), [`config/celery.py`](config/celery.py), and the schedule example below. Nested folders (`migrations/`, `tests/`, `management/commands/`, …) usually **do not** carry their own README; browse the code or use the app README and **[docs/README.md](docs/README.md)** / **[docs/service_api/](docs/service_api/)**. When you add commands or tests, update the app README **by hand** so tables and links stay accurate.

| Package | Notes |
| --- | --- |
| **`config/`** | Django project: [`settings.py`](config/settings.py), [`urls.py`](config/urls.py), [`celery.py`](config/celery.py), [`test_settings.py`](config/test_settings.py); collector schedule template [`boost_collector_schedule.yaml.example`](config/boost_collector_schedule.yaml.example) (copy to `config/boost_collector_schedule.yaml` for a working schedule). |
| [`core/`](core/README.md) | Collector abstractions and `core.operations` (GitHub, Slack, files, markdown). |
| [`boost_collector_runner/`](boost_collector_runner/README.md) | YAML-driven `run_scheduled_collectors` orchestration. |
| [`github_activity_tracker/`](github_activity_tracker/README.md) | GitHub ingest, workspace files, token/rate-limit considerations. |
| [`boost_library_tracker/`](boost_library_tracker/README.md) | Boost metadata + many maintenance commands. |
| [`boost_usage_tracker/`](boost_usage_tracker/README.md) | Usage signals and DB update commands. |
| [`cppa_youtube_script_tracker/`](cppa_youtube_script_tracker/README.md) | Large CLI surface; use `--help` and module docstrings. |
| [`cppa_pinecone_sync/`](cppa_pinecone_sync/README.md) | Pinecone sync entrypoint (namespace + preprocessor contract). |
| [`wg21_paper_tracker/`](wg21_paper_tracker/README.md) | WG21 mailing pipeline and optional GitHub dispatch. |
| [`clang_github_tracker/`](clang_github_tracker/README.md) | Clang / LLVM GitHub activity collection. |
| [`boost_library_docs_tracker/`](boost_library_docs_tracker/README.md) | Boost library docs ingest (requires `pandoc`). |
| [`boost_mailing_list_tracker/`](boost_mailing_list_tracker/README.md) | Boost mailing list ingestion. |
| [`boost_library_usage_dashboard/`](boost_library_usage_dashboard/README.md) | Library usage data for dashboards. |
| [`cppa_slack_tracker/`](cppa_slack_tracker/README.md) | CPPA Slack workspace collection. |
| [`cppa_user_tracker/`](cppa_user_tracker/README.md) | CPPA users and GitHub account linkage. |
| [`discord_activity_tracker/`](discord_activity_tracker/README.md) | Discord activity ingestion (exporter + workspace). |
| [`slack_event_handler/`](slack_event_handler/README.md) | Slack Socket Mode listener (dev `runserver` integration). |

## How it works

- Django project: One Django project with multiple Django apps; all apps share the same settings and database.
- **Architecture / data flow:** See **[docs/Architecture_data_flow.md](docs/Architecture_data_flow.md)** for Mermaid diagrams (sources → collectors → PostgreSQL / workspace → Pinecone) and a per-app component map. Scheduling diagram: [docs/Development_guideline.md](docs/Development_guideline.md#architecture-high-level). For a **curated list of packages with their own README**, see [App-level READMEs](#app-level-readmes) above.
- Workflow: **`boost_collector_runner`** runs app commands from **`config/boost_collector_schedule.yaml`** (via **`run_scheduled_collectors`** and Celery). You can also run individual `manage.py` commands by hand.
- Database: One PostgreSQL database (e.g. `boost_dashboard`); Django ORM and migrations for all apps.
- Configuration: Django settings (`settings.py`) and environment variables (e.g. via `django-environ` or `python-decouple`).

## GitHub tokens

The project supports multiple GitHub tokens for different operations (see `.env.example`):

- **GITHUB_TOKEN** – Fallback when a specific token is not set.
- **GITHUB_TOKENS_SCRAPING** – Comma-separated list for API read/scraping; tokens are used in round-robin to spread rate limits.
- **GITHUB_TOKEN_WRITE** – Used for create PR, create issue, comment on issue, and git push (falls back to GITHUB_TOKEN).

**Operations (shared I/O):** External integrations (GitHub, Slack/markdown helpers, etc.) live under **`core.operations`** (for example **`core.operations.github_ops`**) and are not separate Django apps. See **[docs/operations/](docs/operations/)** and **[docs/operations/github.md](docs/operations/github.md)** for GitHub usage and token mapping.

## Workspace (raw/processed files)

One folder, subfolders per app. For **github_activity_tracker**, sync uses `workspace/github_activity_tracker/<owner>/<repo>/commits|issues|prs/*.json`; files are processed into the DB then removed. Default root: `workspace/` (configurable via `WORKSPACE_DIR`). See [docs/Workspace.md](docs/Workspace.md).

## Documentation

Docs are organized **by topic** (one doc per concern: workflow, workspace, service API, etc.). See **[docs/README.md](docs/README.md)** for the full index.

- [Onboarding.md](docs/Onboarding.md) – First-day orientation for contributors (mental model, app roles, data flow).
- [docs/README.md](docs/README.md) – Per-topic index and how to find app-specific info.
- [Running tests](#running-tests) – How to run the test suite (pytest, coverage) and **Pyright** (`uv run pyright`).
- [Celery](#celery) – How to start the Celery worker and Beat.
- [Celery_test.md](docs/Celery_test.md) – Testing the Celery task (run once, Beat, Redis).
- [operations/](docs/operations/README.md) – **Operations group:** shared I/O (GitHub, Discord, etc.); index and per-operation docs.
- [Architecture_data_flow.md](docs/Architecture_data_flow.md) – High-level data flow (collectors, DB, Pinecone).
- [How_to_add_a_collector.md](docs/How_to_add_a_collector.md) – Checklist for adding a new collector command.
- [operations/github.md](docs/operations/github.md) – GitHub layer (clone, push, fetch file, create PR/issue/comment) and token use.
- [Deployment.md](docs/Deployment.md) – CI/CD pipeline, GitHub secrets, server setup, and deploy script behavior.
- [Workspace.md](docs/Workspace.md) – Workspace layout and usage for file processing.
- [Schema.md](docs/Schema.md) – Database schema and table relationships.
- [Development_guideline.md](docs/Development_guideline.md) – Development setup, app requirements, and step-by-step workflow.
- [CONTRIBUTING.md](CONTRIBUTING.md) – Service layer (single place for writes), **regenerating service API docs** (`scripts/generate_service_docs.py`), and contributor guidelines.
- [Service_API.md](docs/Service_API.md) – API reference and index for all service layer functions.
- [service_api/](docs/service_api/) – Per-app service API docs (name, description, parameters, return types, validation).

## Deployment

The project deploys automatically over SSH after CI passes. Pushes to `develop` deploy to staging; pushes to `main` deploy to production.

See **[docs/Deployment.md](docs/Deployment.md)** for:

- Required environment secrets (`SSH_HOST`, `SSH_USER`, `SSH_PRIVATE_KEY`) and optional `SSH_PORT` (defaults to `22`) — set per environment (production / staging)
- GitHub Environments setup (approval gates for production)
- One-time server setup (prerequisites, `.env`, SSH key)
- Deploy script behavior and override options

## Branching strategy

**GitHub’s configured default branch for this repository is `develop`.**

- **main** – Default/production branch (stable, release-ready code).
- **develop** – Development branch (active integration and feature work).
- Feature branches: Create from `develop`. Do not branch from `main` for day-to-day work.
- Pull requests: Open PRs against `develop`; merge to `main` for releases.
