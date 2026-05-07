# Boost Data Collector - Django project

## Overview

Boost Data Collector is a Django project that collects and manages data from various Boost-related sources. The project has multiple Django apps in one repository. All apps share one virtual environment, one database (PostgreSQL), and the same Django settings. Each app exposes one or more management commands (e.g. `run_boost_library_tracker`). Production scheduling uses **Celery Beat** and **`config/boost_collector_schedule.yaml`** via **`run_scheduled_collectors`** (see [docs/Workflow.md](docs/Workflow.md)).

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

## Running tests

The project uses **pytest** with **pytest-django**. Tests run against `config.test_settings` (SQLite in-memory by default; set `DATABASE_URL` to use PostgreSQL).

1. Install test dependencies (once):

```bash
pip install -r requirements-dev.txt
```

2. Run the full test suite:

```bash
python -m pytest
```

3. Optional: run with coverage and enforce a minimum percentage locally:

```bash
python -m pytest --tb=short --cov=. --cov-report=term-missing --cov-fail-under=90
```

Coverage writes a local **`.coverage`** file (binary SQLite data used by `coverage.py`; safe to delete). It is listed in `.gitignore`.

**PostgreSQL parity (recommended before merging DB-sensitive changes):** GitHub Actions runs the full suite against Postgres (`DATABASE_URL` in `.github/workflows/actions.yml`; tests use `127.0.0.1` for a stable loopback connection). Locally, `pytest.ini` defaults to SQLite in-memory when `DATABASE_URL` is unset (`config.test_settings`). Run the full suite against Postgres when you touch JSONB, enums, or locks, for example:

```bash
# Linux / macOS
export DATABASE_URL=postgres://postgres:postgres@127.0.0.1:5432/postgres
python -m pytest
```

```bash
# Windows (Command Prompt)
set DATABASE_URL=postgres://postgres:postgres@127.0.0.1:5432/postgres
python -m pytest
```

4. Run a subset of tests (e.g. one app or one file):

```bash
python -m pytest cppa_user_tracker/tests/ -v
python -m pytest github_activity_tracker/tests/test_sync_utils.py -v
```

CI runs pytest with coverage (`--cov`, HTML/XML reports). To match a **local** coverage gate, use **`--cov-fail-under=90`** (see step 3 above). If coverage fails locally or you need a fresh test DB schema after model changes, run once with `python -m pytest --create-db`.

See [docs/Development_guideline.md](docs/Development_guideline.md#testing-workflow) for when to run tests during development.

## Project structure

```
boost-data-collector/
├── manage.py
├── requirements.txt
├── .env.example
├── README.md
├── config/ or <project_name>/   # Django project settings (settings.py)
├── docs/                         # Documentation (per-topic)
│   ├── README.md                 # Topic index
│   ├── operations/               # Shared I/O (GitHub, Discord, etc.)
│   │   ├── README.md
│   │   └── github.md
│   ├── service_api/              # Per-app service API
│   ├── Workflow.md
│   ├── Schema.md
│   └── ...
├── workspace/                    # Raw/processed files (see docs/Workspace.md)
│   ├── github_activity_tracker/
│   ├── boost_library_tracker/
│   ├── ...
│   └── shared/
|   (Django Apps)
├── cppa_user_tracker/
├── github_activity_tracker/
├── core/                         # Shared utilities (e.g. collector base types)
└──     ...
```

Each Django app can expose management commands in `management/commands/`. All apps are in `INSTALLED_APPS` and use the shared database.

## How it works

- Django project: One Django project with multiple Django apps; all apps share the same settings and database.
- **Architecture / data flow:** See **[docs/Architecture_data_flow.md](docs/Architecture_data_flow.md)** for Mermaid diagrams (sources → collectors → PostgreSQL / workspace → Pinecone) and a per-app component map. Scheduling diagram: [docs/Development_guideline.md](docs/Development_guideline.md#architecture-high-level).
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
- [Running tests](#running-tests) – How to run the test suite (pytest, coverage).
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
- [Contributing.md](docs/Contributing.md) – Service layer (single place for writes) and contributor guidelines.
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

- **main** – Default/production branch (stable, release-ready code).
- **develop** – Development branch (active integration and feature work).
- Feature branches: Create from `develop`. Do not branch from `main` for day-to-day work.
- Pull requests: Open PRs against `develop`; merge to `main` for releases.
