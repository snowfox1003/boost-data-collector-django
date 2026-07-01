# Tutorial: building a collector from scratch

This tutorial walks through creating a new data collector end to end: scaffolding with **`startcollector`**, **`AbstractCollector`** hooks, tests, YAML/Celery scheduling, and production readiness. It is the narrative companion to the checklist in [How_to_add_a_collector.md](How_to_add_a_collector.md).

**Worked example:** a fictional app **`heartbeat_demo`**. You create it locally with `startcollector`; it is **not** committed to the repository. For real in-repo patterns, see [cppa_user_tracker](../cppa_user_tracker/) (minimal inline collector) and [wg21_paper_tracker](../wg21_paper_tracker/) (split `collectors.py` + rich CLI).

---

## 0. Prerequisites and outcomes

### Before you start

1. Complete project setup from the root [README.md](../README.md) (venv, `DATABASE_URL`, `migrate`).
2. Skim [Onboarding.md](Onboarding.md) §1 — five ideas: collectors are management commands; writes go through **`services.py`**; scheduling is YAML-driven.
3. Optional: [Architecture_data_flow.md](Architecture_data_flow.md) for where your collector fits in the pipeline.

### What you will be able to do

After this tutorial you can:

- Scaffold a collector app with `python manage.py startcollector <app_label>`
- Explain why **`validate_config`**, **`collect`**, and **`sync_pinecone`** exist and who calls them
- Run and test the collector locally with pytest (PostgreSQL)
- Register the command in **`config/boost_collector_schedule.yaml`** — `startcollector` appends a commented stub; you move it to the right group and enable when ready
- Know what happens when Celery Beat and deployment run your collector

---

## 1. Scaffolding with `startcollector`

Run all commands from the **repository root** so the new app sits next to the other Django apps.

### Preview, then create

```bash
python manage.py startcollector heartbeat_demo --dry-run
python manage.py startcollector heartbeat_demo
```

`--dry-run` prints planned paths, project registration previews, and a preview of `schedule_snippet.yaml` without writing files.

Use **`--no-register`** to scaffold the app package only (no edits to `config/settings.py`, schedule YAML, `.importlinter`, or cross-app docs).

### What gets generated (14 app files + project registration)

`startcollector` writes a full Django app package. When run from the **repository root** (default `--path .`), it also updates four project files via [collector_registry.py](../core/management/collector_registry.py). Registration is skipped when `--path` points elsewhere (for example pytest scratch dirs or CI) or when **`--no-register`** is set. File bodies are built in [startcollector.py](../core/management/commands/startcollector.py).

```text
heartbeat_demo/
  __init__.py
  admin.py
  apps.py
  models.py
  services.py
  views.py
  schedule_snippet.yaml
  migrations/
    __init__.py
    0001_initial.py
  management/
    __init__.py
    commands/
      __init__.py
      run_heartbeat_demo.py
  tests/
    __init__.py
    test_run_heartbeat_demo_command.py
```

```mermaid
flowchart TB
  subgraph scaffold [startcollector app package]
    models[models.py RunState stub]
    services[services.py record_run]
    runCmd["management/commands/run_heartbeat_demo.py"]
    mig[migrations/0001_initial.py]
    snippet[schedule_snippet.yaml]
    test[tests/test_run_heartbeat_demo_command.py]
  end
  subgraph register [Auto at repo root]
    installed[INSTALLED_APPS]
    yaml[boost_collector_schedule.yaml commented EOF]
    importlinter[.importlinter root_packages]
    crossapp[cross-app-dependencies inventory stub]
  end
  subgraph manual [You do manually]
    migrate[migrate]
    scheduleMove[Move schedule to correct group]
    customize[Customize docs and domain logic]
  end
  scaffold --> register --> manual
```

| File | Purpose |
|------|---------|
| `apps.py` | `HeartbeatDemoConfig` with `name = "heartbeat_demo"` |
| `models.py` | Stub `HeartbeatDemoRunState` (`source_key`, `run_count`, `updated_at`) |
| `services.py` | Stub `record_run()` — **all DB writes** for this app should stay here |
| `management/commands/run_heartbeat_demo.py` | `HeartbeatDemoCollector` + `Command(BaseCollectorCommand)` |
| `migrations/0001_initial.py` | Hand-written initial migration matching the stub model |
| `schedule_snippet.yaml` | Commented YAML reference (also appended to shared schedule file at repo root) |
| `tests/test_run_heartbeat_demo_command.py` | Smoke test via `call_command` |

**Auto-registered at repo root:** `INSTALLED_APPS` entry in [config/settings.py](../config/settings.py), commented schedule block at EOF of [config/boost_collector_schedule.yaml](../config/boost_collector_schedule.yaml), `root_packages` entry in [`.importlinter`](../.importlinter), and stub inventory row in [cross-app-dependencies.md](cross-app-dependencies.md).

**Not generated:** `collectors.py` (split from `run_*.py` when the command grows — §2.5).

### Design decisions (why the scaffold looks like this)

| Decision | Why |
|----------|-----|
| One Django app per collector domain | Shared PostgreSQL, isolated `services.py`, clear ownership in CODEOWNERS |
| Command name `run_{app_label}` | Must match YAML `command:` and what Celery/`call_command` invoke |
| Stub run-state model + `record_run()` | Proves migrations and the service-layer write path before real domain logic |
| Hand-written `0001_initial.py` | Migration matches stub `models.py` on day one; run **`makemigrations`** yourself only after you change models |
| Commented schedule block at EOF | Schedule placement is reviewed in PR; avoids Beat calling a command in the wrong group |
| Collector class inside `run_*.py` initially | Smallest first PR; split into `collectors.py` when the command grows (§2.5) |

### Steps after scaffold

When run from the repo root, **`startcollector` already registered the app**. You still need to:

1. Run **`python manage.py migrate`**.
2. Run **`python manage.py run_heartbeat_demo`** — expect success output and one row in `heartbeat_demo_heartbeatdemorunstate` (table name from Django’s model naming).
3. Review the commented schedule block at the end of [config/boost_collector_schedule.yaml](../config/boost_collector_schedule.yaml) — move it under the correct **`groups.<name>.tasks`**, uncomment, and keep **`enabled: false`** until production-ready (§5).
4. Customize the stub row for your app in [cross-app-dependencies.md](cross-app-dependencies.md); expand §1–§3 if you add cross-app imports or FKs.
5. When `services.py` grows, run **`python scripts/generate_service_docs.py`** and commit `docs/service_api/` updates.

The generated collector follows this shape (abbreviated):

```python
from core.collectors import AbstractCollector, GenericTrackerResult

class HeartbeatDemoCollector(AbstractCollector):
  @property
  def name(self) -> str:
    return "heartbeat_demo"

  def validate_config(self) -> None:
    if not self.source_key or not self.source_key.strip():
      raise ValueError("source_key must not be empty")

  def collect(self) -> GenericTrackerResult:
    _, created = services.record_run(source_key=self.source_key.strip())
    return GenericTrackerResult.ok(runs=1, created=int(created))

class Command(BaseCollectorCommand):
  def get_collector(self, **_options: Any) -> AbstractCollector:
    return HeartbeatDemoCollector(stdout=self.stdout, style=self.style)
```

Note: the scaffold stores `source_key` on the collector but does **not** wire `--source-key` on the command until you add it (§3.1). That is intentional practice for your first edit.

If you used **`--path`** outside the repo root or **`--no-register`**, follow the manual registration list printed by the command (`INSTALLED_APPS`, schedule, `.importlinter`, cross-app docs, then **`migrate`**).

---

## 2. AbstractCollector hooks and lifecycle

Collectors are not auto-discovered as Python classes. Django finds **`management/commands/run_*.py`** under installed apps. Your collector class is built by **`BaseCollectorCommand.get_collector()`** and executed in a fixed two-phase lifecycle.

### Sequence

```mermaid
sequenceDiagram
  participant Cmd as BaseCollectorCommand
  participant Col as AbstractCollector
  Cmd->>Col: get_collector(options)
  Cmd->>Col: run()
  Col->>Col: validate_config()
  Col->>Col: load_incremental_state()
  Col->>Col: collect() -> TrackerResult
  Cmd->>Cmd: log TrackerResult counts/errors
  Cmd->>Col: sync_pinecone()
```

Implementation: [core/collectors/command_base.py](../core/collectors/command_base.py) `handle()` calls `get_collector`, then `_run_collector_phase(collector, collector.run)`, then `_run_collector_phase(collector, collector.sync_pinecone)`.

`AbstractCollector.run()` is **concrete** — do not override it. It runs `validate_config()` then `collect()` ([core/collectors/base_collector.py](../core/collectors/base_collector.py)).

### Hook reference

| Hook | Who calls it | Responsibility | Tutorial example |
|------|----------------|----------------|------------------|
| `name` | `handle_error` logging | Stable slug for metrics/alerts | `"heartbeat_demo"` |
| `validate_config()` | `run()` before I/O | Fast checks: env, CLI, empty keys | Reject empty `source_key` |
| `collect()` | `run()` | Orchestration; delegate DB to `services.py`; return `TrackerResult` | `GenericTrackerResult.ok(...)` after `services.record_run(...)` |
| `run()` | Command | Template: validate → collect | Do not override |
| `handle_error(exc)` | Command on non-`CommandError` | Log with `classify_failure` | Default is enough for most apps |
| `sync_pinecone()` | Command after `run` | Post-run vector sync; default no-op | See §2.4 |

### Error taxonomy (important for reviews)

| Exception | Behavior |
|-----------|----------|
| `django.core.management.base.CommandError` | Logged by command with `failure_category=command`; **not** passed to `handle_error`; re-raised |
| Any other `Exception` | `collector.handle_error(exc)` then re-raised (non-zero exit for scheduler) |

During each phase the command sets **`collector._error_phase`** to `"run"` or `"sync_pinecone"` and clears it in `finally` (even if logging fails).

**When to use `CommandError`:** invalid CLI combinations, missing required env vars that should read as “user/config error” (§3.3).

**When to let other exceptions propagate:** API failures, DB errors — `handle_error` classifies them via [core/errors.py](../core/errors.py) `classify_failure()` into `CollectorFailureCategory` values for structured logs.

**Declaring app-specific errors for classification:**

- API payload validation at ingestion boundaries → subclass [`CollectorValidationError`](../core/errors.py) (see `GitHubApiValidationError`, `SlackApiValidationError`).
- Credential rejection → subclass [`AuthenticationError`](../core/errors.py) (or multiply-inherit, e.g. `AuthError(CollectorError, AuthenticationError)`).
- Classification uses **exception type hierarchy**, not module paths — moving or renaming a module does not change `failure_category`.
- Third-party SDK errors are handled centrally in [`core/failure_classifiers.py`](../core/failure_classifiers.py); override `handle_error` only when you need finer buckets than `unknown`.

Override `handle_error` only when the default classifier does not match your domain (see [How_to_add_a_collector.md](How_to_add_a_collector.md#3-shared-abstractions-recommended)).

### Optional: `sync_pinecone()`

Default is a no-op. Collectors that index after fetch override it, often by calling another management command, e.g. `cppa_slack_tracker` → `run_cppa_pinecone_sync`. The tutorial stub does not implement this.

### When to extract `collectors.py`

Keep collector + command in **`run_heartbeat_demo.py`** while the command stays small (rough guide: under ~80 lines of collector logic).

Split when:

- CLI parsing and collector logic make `run_*.py` hard to navigate
- You want unit tests on the collector without loading the Django command

**Production example:** [wg21_paper_tracker/collectors.py](../wg21_paper_tracker/collectors.py) + thin [run_wg21_paper_tracker.py](../wg21_paper_tracker/management/commands/run_wg21_paper_tracker.py).

**Minimal in-repo example (inline, like scaffold):** [cppa_user_tracker/management/commands/run_cppa_user_tracker.py](../cppa_user_tracker/management/commands/run_cppa_user_tracker.py).

---

## 3. Evolving the worked example

These three edits turn the stub into a realistic collector shape. Apply them on your local `heartbeat_demo` app (do not commit the app unless you are shipping a real feature).

### 3.1 Wire `--source-key` on the command

The scaffold collector already accepts `source_key` in `__init__`. Add CLI wiring on `Command`:

```python
# heartbeat_demo/management/commands/run_heartbeat_demo.py

class Command(BaseCollectorCommand):
    help = "Run the heartbeat_demo collector."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--source-key",
            default="default",
            help="Logical source key for HeartbeatDemoRunState.",
        )

    def get_collector(self, **options: Any) -> AbstractCollector:
        return HeartbeatDemoCollector(
            stdout=self.stdout,
            style=self.style,
            source_key=options["source_key"],
        )
```

Run: `python manage.py run_heartbeat_demo --source-key=prod`.

### 3.2 Service layer

Rename or extend `record_run` as your domain grows. **Rule:** all creates/updates/deletes for `heartbeat_demo` models go through **`heartbeat_demo/services.py`** — not from `collect()` directly. See [CONTRIBUTING.md](../CONTRIBUTING.md#service-layer-single-place-for-writes).

When you add public service functions, regenerate API docs:

```bash
python scripts/generate_service_docs.py
# or one app: python scripts/generate_service_docs.py --app heartbeat_demo
```

### 3.3 Validation and `CommandError`

Demonstrate config errors vs runtime errors. Example: require an env var for a hypothetical API:

```python
import os
from django.core.management.base import CommandError

def validate_config(self) -> None:
    if not self.source_key or not self.source_key.strip():
        raise ValueError("source_key must not be empty")
    if not os.environ.get("HEARTBEAT_DEMO_API_KEY"):
        raise CommandError(
            "HEARTBEAT_DEMO_API_KEY is not set. "
            "Add it to .env and document it in .env.example."
        )
```

Document new variables in **`.env.example`** and, if needed, **`docs/operations/`**.

### Anti-patterns

- Calling `HeartbeatDemoRunState.objects.create(...)` from `collect()` instead of `services.py`
- Importing another tracker app’s models without updating [cross-app-dependencies.md](cross-app-dependencies.md)
- Setting **`enabled: true`** in YAML before the app is merged and migrated

---

## 4. Testing

The project uses **pytest + pytest-django** with **PostgreSQL only** (`config.test_settings`). See [README.md](../README.md#running-tests).

### Test layers

| Layer | What to test | How |
|-------|----------------|-----|
| Service | `record_run` create/increment | `@pytest.mark.django_db`, assert on ORM |
| Command integration | Full `call_command` path | Scaffold smoke test (below) |
| Collector unit | `validate_config` / `collect` with mocks | `@patch` on `services.record_run` |
| Scheduler (advanced) | YAML loading / strict mode | [boost_collector_runner/tests/test_schedule_config.py](../boost_collector_runner/tests/test_schedule_config.py) |

### Scaffold smoke test (already generated)

```python
@pytest.mark.django_db
def test_run_heartbeat_demo_writes_success():
    out = StringIO()
    call_command("run_heartbeat_demo", stdout=out, verbosity=0)
    assert "completed" in out.getvalue().lower()
```

### Expand: service test

```python
# heartbeat_demo/tests/test_services.py
import pytest
from heartbeat_demo.models import HeartbeatDemoRunState
from heartbeat_demo.services import record_run


@pytest.mark.django_db
def test_record_run_creates_and_increments():
    row1, created1 = record_run(source_key="alpha")
    assert created1 is True
    assert row1.run_count == 1

    row2, created2 = record_run(source_key="alpha")
    assert created2 is False
    assert row2.id == row1.id
    assert row2.run_count == 2
```

### Expand: collector unit test (mock services)

Pattern from [wg21_paper_tracker/tests/test_collectors.py](../wg21_paper_tracker/tests/test_collectors.py):

```python
from unittest.mock import patch
import pytest
from heartbeat_demo.management.commands.run_heartbeat_demo import HeartbeatDemoCollector


def test_validate_config_rejects_empty_source_key():
    collector = HeartbeatDemoCollector(stdout=None, style=None, source_key="  ")
    with pytest.raises(ValueError):
        collector.validate_config()


@patch("heartbeat_demo.services.record_run")
def test_collect_calls_service(mock_record_run):
    mock_record_run.return_value = (None, True)
    collector = HeartbeatDemoCollector(stdout=None, style=None, source_key="k1")
    collector.collect()
    mock_record_run.assert_called_once_with(source_key="k1")
```

### Run tests locally

```bash
docker compose -f docker-compose.test.yml up -d
export DATABASE_URL=postgres://postgres:postgres@127.0.0.1:5433/postgres
export SECRET_KEY=for-local-only
export DJANGO_SETTINGS_MODULE=config.test_settings

uv run pytest heartbeat_demo/tests/ -v
uv run pytest   # full suite before PR
uv run pyright  # typing, matches CI
```

### CI

- **Lint job:** [scripts/validate_collector_scaffold.py](../scripts/validate_collector_scaffold.py) recreates a throwaway app under `.test_artifacts/`, then runs ruff and scoped pyright.
- **Test job:** full `pytest` with **90%** coverage gate (`.github/workflows/actions.yml`).

---

## 5. Celery scheduling

Scheduling is **YAML-driven** — no Python change to add a Beat entry. Full reference: [Workflow.md §2](Workflow.md#2-boost-collector-runner-and-yaml-schedule).

### Author checklist

1. Find the commented **`startcollector: heartbeat_demo`** block at the end of [config/boost_collector_schedule.yaml](../config/boost_collector_schedule.yaml) (appended automatically when you scaffold at repo root).
2. Move the task under the right **`groups.<name>.tasks`** (pick a group that matches runtime dependencies, e.g. `github` for GitHub-related work) and uncomment the lines.
3. Keep **`enabled: false`** until the app is on `develop`/`main` and migrated.
4. After merge, flip **`enabled: true`** per team policy (same PR or follow-up).

Example entry:

```yaml
groups:
  github:
    default_time: "00:05"
    tasks:
      # ... existing tasks ...
      - command: run_heartbeat_demo
        schedule: daily
        enabled: false
        args: ["--source-key", "default"]
```

The **`command`** value must match the Django management command name (filename `run_heartbeat_demo.py` → command `run_heartbeat_demo`).

### How Beat runs your collector

```mermaid
flowchart LR
  beat[CeleryBeat] --> task[run_scheduled_collectors_task]
  task --> mgmt[run_scheduled_collectors]
  mgmt --> cmd[run_heartbeat_demo]
```

- [config/settings.py](../config/settings.py) sets `CELERY_BEAT_SCHEDULE` from YAML via `get_beat_schedule()`.
- [boost_collector_runner/tasks.py](../boost_collector_runner/tasks.py) `@shared_task` `run_scheduled_collectors_task` calls `call_command("run_scheduled_collectors", ...)`.
- Within one batch, collectors in a group run **sequentially**; different groups can run in parallel on workers.

### Local verification

```bash
# Run one collector by hand
python manage.py run_heartbeat_demo --source-key=default

# Run a scheduled group (same as Beat would batch)
python manage.py run_scheduled_collectors --schedule daily --group github

# Optional: trigger Celery task directly (worker must be running)
# See docs/Celery_test.md
```

Docker: start **`celery_worker`** and **`celery_beat`** per [Docker.md](Docker.md).

**Strict mode:** With `DEBUG=False` or `BOOST_COLLECTOR_SCHEDULE_STRICT=True`, invalid YAML fails at settings import so Beat does not start with an empty schedule.

---

## 6. Deployment and production readiness

Short path; details in [Deployment.md](Deployment.md) and [GCP_Production_Checklist.md](GCP_Production_Checklist.md).

| Step | Action |
|------|--------|
| PR merged | Set `enabled: true` in YAML when ready for production runs |
| Deploy | `docker compose` with `web`, `celery_worker`, `celery_beat`, Redis |
| Health | `GET /health/` returns **503** while `HEALTH_ENFORCE_COLLECTOR_FRESHNESS=true` until daily YAML groups have successful runs |
| Secrets | New env vars in `.env.example`; ops notes under `docs/operations/` if using external APIs |

Production-scale references:

- **`github_activity_tracker`** — full fetch, workspace, Pinecone pipeline
- **`wg21_paper_tracker`** — split `collectors.py`, rich CLI, service-backed pipeline

---

## 7. Checklist and further reading

### Copy-paste checklist

- [ ] `python manage.py startcollector <app_label>` from repo root (registers project files automatically)
- [ ] `python manage.py migrate`
- [ ] Implement real logic in `services.py`; keep `collect()` thin
- [ ] Subclass `AbstractCollector` + `BaseCollectorCommand` (or split `collectors.py` when large)
- [ ] `validate_config` for fast checks; `CommandError` for bad config
- [ ] Tests: service + command (+ collector unit tests with mocks)
- [ ] Move commented schedule block to the correct group; set `enabled: false` until ready
- [ ] Customize `cross-app-dependencies.md` stub; expand if importing other apps
- [ ] `.env.example` + ops docs for new secrets
- [ ] `generate_service_docs.py` when adding public service functions
- [ ] `uv run pytest` and `uv run pyright` before PR
- [ ] Enable task in YAML after deploy/migrate
- [ ] Verify `/health/` and optional `run_scheduled_collectors` on staging

### Further reading

| Topic | Doc |
|-------|-----|
| Checklist / contracts | [How_to_add_a_collector.md](How_to_add_a_collector.md) |
| `startcollector` + service layer | [CONTRIBUTING.md](../CONTRIBUTING.md#creating-a-new-collector) |
| YAML schedules | [Workflow.md](Workflow.md) |
| Core collector API | [Core_public_API.md](Core_public_API.md) |
| Data flow | [Architecture_data_flow.md](Architecture_data_flow.md) |
| Cross-app imports | [cross-app-dependencies.md](cross-app-dependencies.md) |
| Deploy / GCP | [Deployment.md](Deployment.md), [GCP_Production_Checklist.md](GCP_Production_Checklist.md) |
| Celery manual test | [Celery_test.md](Celery_test.md) |
| Service function reference | [Service_API.md](Service_API.md) |
