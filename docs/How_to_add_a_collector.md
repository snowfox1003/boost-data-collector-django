# How to add a collector

This checklist assumes you already have a Django app (or are creating one) with a `management/commands/run_<your_app>.py` entry point. For a high-level diagram and GitHub pipeline notes, see the **Architecture** section in [Development_guideline.md](Development_guideline.md).

## 1. App and command

1. Add the app to `INSTALLED_APPS` in `config/settings.py` if it is new.
2. Implement `management/commands/run_<name>.py` so it exits with status **0** on success and non-zero on failure (so `run_scheduled_collectors` can detect failures).

## 2. Register the command in YAML

Add a task under the right group in `config/boost_collector_schedule.yaml` (see [Workflow.md](Workflow.md#2-boost-collector-runner-and-yaml-schedule)). That file is **committed** to the repository; [`config/boost_collector_schedule.yaml.example`](../config/boost_collector_schedule.yaml.example) only points to it. Celery Beat runs **`boost_collector_runner.tasks.run_scheduled_collectors_task`** per group and schedule.

## 3. Shared abstractions (recommended)

Stable imports live under **`core.collectors`** (re-exported in [`core/collectors/__init__.py`](../core/collectors/__init__.py)); see the **Collectors** table in [Core_public_API.md](Core_public_API.md#collectors) for `AbstractCollector`, `CollectorBase`, `CollectorRunnable`, `BaseCollectorCommand`, and `DjangoCommandCollector`.

- **Preferred:** Subclass **`AbstractCollector`** and implement a stable `name` property, `validate_config()`, and `collect()`. The base provides concrete `run()` as `validate_config()` then `collect()`, plus `handle_error()` / `sync_pinecone()` aligned with legacy **`CollectorBase`**. Use **`BaseCollectorCommand`** so the management command stays thin (`get_collector()` returns any **`CollectorRunnable`**: `run`, `sync_pinecone`, `handle_error`).
- **Legacy:** Subclass **`CollectorBase`** and implement `run()` only (same error/Pinecone hooks). New work should prefer **`AbstractCollector`**.
- **`DjangoCommandCollector`** remains available for tests or internal `call_command` wrappers.

### Collector contracts (source of truth)

The detailed contracts (abstract methods, lifecycle hooks, error handling, template-method flow) live in the **class docstrings** in the codebase—read these when wiring a new collector:

- [`core/collectors/base.py`](../core/collectors/base.py) — `CollectorBase`
- [`core/collectors/command_base.py`](../core/collectors/command_base.py) — `BaseCollectorCommand`
- [`core/collectors/base_collector.py`](../core/collectors/base_collector.py) — `CollectorRunnable`, `AbstractCollector`, `_CollectorLifecycleMixin`

**At a glance:** `BaseCollectorCommand` calls `get_collector(**options)` then runs `run` and `sync_pinecone`. During each phase it sets `collector._error_phase` (for example `"run"`) and clears it in a `finally` block. `django.core.management.base.CommandError` is logged with `failure_category="command"` and is **not** passed to `handle_error`; any other exception is passed to `handle_error`, which logs using **`classify_failure()`** from [`core/errors.py`](../core/errors.py) (the function maps exceptions to **`CollectorFailureCategory`** values—it is not a method on the enum). Override `handle_error` when the default classifier does not fit your domain.

## 4. Skeleton collector (minimal copy-paste example)

This section is a **canonical minimal pattern**: the management command is only responsible for parsing options and returning a collector from `get_collector()` (often ~10–15 lines). The **`AbstractCollector` subclass** implements `name`, `validate_config`, and `collect` (orchestration); `BaseCollectorCommand` still calls `run()`, which the base implements as validate-then-collect. The **service layer** (`services.py`) is the main place for DB and API logic—match the project rule that writes go through services (see [Contributing.md](Contributing.md#service-layer-single-place-for-writes)).

Keep imports and calls inside `collect()` going through `services.py` (for example `import my_skeleton_tracker.services as services` and only call functions from that module) so the write path stays obvious.

**Not a repo artifact:** The snippets below use a placeholder app name `my_skeleton_tracker`. They are meant to be copied into a **new** Django app directory and adjusted; this repository does not ship that app. For a **full** production-sized collector (fetch, raw files, Pinecone, many models), use [`github_activity_tracker/`](../github_activity_tracker/) as reference; use this skeleton to learn the shape without noise.

**Failure taxonomy:** `AbstractCollector.handle_error` (same mixin as `CollectorBase`) logs with [`classify_failure`](../core/errors.py) so log records include a stable `failure_category` (see [`CollectorFailureCategory`](../core/errors.py)). When `name` is set, logs use that slug for the `collector=` field. Override `handle_error` only when you need extra context; map domain errors to categories there if the default classifier is not enough.

### Layout (after find-replace)

Replace `my_skeleton_tracker` / `run_my_skeleton_tracker` with your real app and command names everywhere below.

```text
my_skeleton_tracker/
  __init__.py
  apps.py
  collectors.py
  models.py
  services.py
  management/
    __init__.py
    commands/
      __init__.py
      run_my_skeleton_tracker.py
  tests/
    __init__.py
    test_skeleton_collector.py
```

`management/__init__.py`, `management/commands/__init__.py`, `tests/__init__.py`, and the package `__init__.py` can be empty files.

### Import rules (read before pasting)

- **Do import** from **`core`** using the public **`core.collectors`** surface (e.g. `from core.collectors import AbstractCollector, BaseCollectorCommand`, as in [Core_public_API.md — Collectors](Core_public_API.md#collectors)) and **`core.errors`** if you customize error handling, plus **Django**.
- **Do import** from **your own app** (`my_skeleton_tracker.services`, `my_skeleton_tracker.collectors`, etc.).
- **Do not import** from other tracker apps in the collector or command unless you have a deliberate integration; shared protocols belong in `core` (see [Core_public_API.md](Core_public_API.md) if applicable).

### `models.py`

```python
# my_skeleton_tracker/models.py
"""Customize: model fields for your domain. This stub proves migrations + ORM wiring."""

from django.db import models


class SkeletonRun(models.Model):
    """One row per logical source key; stub for incremental or heartbeat-style state."""

    # CUSTOMIZE: replace source_key semantics (e.g. workspace id, channel id).
    source_key = models.CharField(max_length=128, unique=True, db_index=True)
    run_count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["source_key"]
```

### `services.py`

```python
# my_skeleton_tracker/services.py
"""Customize: add real validation, idempotency, and side effects. All writes for this app go here."""

from __future__ import annotations

from django.db import transaction

from my_skeleton_tracker.models import SkeletonRun


@transaction.atomic
def record_skeleton_run(*, source_key: str) -> tuple[SkeletonRun, bool]:
    """
    Increment run_count for source_key, creating the row if missing.

    Returns (instance, created) like get_or_create-style helpers elsewhere in the project.
    """
    # CUSTOMIZE: replace with your real upsert logic.
    if not source_key or not source_key.strip():
        raise ValueError("source_key must not be empty")
    key = source_key.strip()
    obj, created = SkeletonRun.objects.select_for_update().get_or_create(
        source_key=key,
        defaults={"run_count": 0},
    )
    obj.run_count += 1
    obj.save(update_fields=["run_count", "updated_at"])
    return obj, created
```

### `collectors.py`

```python
# my_skeleton_tracker/collectors.py
"""Customize: name + validate_config + collect; optional sync_pinecone() for post-run indexing."""

from __future__ import annotations

import logging

from core.collectors import AbstractCollector
from my_skeleton_tracker.services import record_skeleton_run

# If you override handle_error, you can log or map errors explicitly, e.g.:
# from core.errors import CollectorFailureCategory, classify_failure

logger = logging.getLogger(__name__)


class MySkeletonCollector(AbstractCollector):
    """
    STANDARD: AbstractCollector gives run() = validate_config + collect, handle_error
    (uses classify_failure / CollectorFailureCategory), and a no-op sync_pinecone.
    CUSTOMIZE: constructor options from the management command.
    """

    def __init__(self, *, source_key: str = "default") -> None:
        self.source_key = source_key

    @property
    def name(self) -> str:
        return "my_skeleton_tracker"

    def validate_config(self) -> None:
        if not self.source_key or not self.source_key.strip():
            raise ValueError("source_key must not be empty")

    def collect(self) -> None:
        obj, created = record_skeleton_run(source_key=self.source_key.strip())
        logger.info(
            "skeleton run recorded source_key=%s run_count=%s created=%s",
            obj.source_key,
            obj.run_count,
            created,
        )

    # STANDARD: omit sync_pinecone unless you post-process (e.g. Pinecone); default is no-op.
```

### `management/commands/run_my_skeleton_tracker.py`

```python
# my_skeleton_tracker/management/commands/run_my_skeleton_tracker.py
"""STANDARD: BaseCollectorCommand runs run() then sync_pinecone() with shared error handling."""

from __future__ import annotations

from typing import Any

from core.collectors import BaseCollectorCommand, CollectorRunnable
from my_skeleton_tracker.collectors import MySkeletonCollector


class Command(BaseCollectorCommand):
    """CUSTOMIZE: help string and CLI flags for your collector."""

    help = "Run my_skeleton_tracker (minimal documentation example)."

    def add_arguments(self, parser) -> None:
        # CUSTOMIZE: add real flags (--since, --dry-run, etc.).
        parser.add_argument(
            "--source-key",
            default="default",
            help="Stub key for SkeletonRun.source_key.",
        )

    def get_collector(self, **options: Any) -> CollectorRunnable:
        return MySkeletonCollector(source_key=options["source_key"])
```

### `apps.py`

```python
# my_skeleton_tracker/apps.py
from django.apps import AppConfig


class MySkeletonTrackerConfig(AppConfig):
    # STANDARD: BigAutoField is project-typical.
    default_auto_field = "django.db.models.BigAutoField"
    # CUSTOMIZE: must match the Python package directory name.
    name = "my_skeleton_tracker"
```

### YAML schedule entry

Add under an existing group in `config/boost_collector_schedule.yaml` (see [Workflow.md](Workflow.md#2-boost-collector-runner-and-yaml-schedule) and the example file). Keep **`enabled: false`** until the app is merged and migrations exist, so Beat does not invoke a missing command.

```yaml
# CUSTOMIZE: group name, command name, and schedule.
groups:
  examples:
    default_time: "05:00"
    tasks:
      - command: run_my_skeleton_tracker
        schedule: daily
        enabled: false
        args: ["--source-key", "default"]
```

### Wire-up after copy-paste

1. Register **`"my_skeleton_tracker.apps.MySkeletonTrackerConfig"`** in **`INSTALLED_APPS`** in `config/settings.py` (or the short app label if your Django version auto-discovers `apps.py`; the full path is unambiguous).
2. Run **`python manage.py makemigrations my_skeleton_tracker`** then **`python manage.py migrate`**.
3. Run **`python manage.py run_my_skeleton_tracker`** (optionally with `--source-key`).

### `tests/test_skeleton_collector.py`

Tests use the same **pytest + pytest-django** stack as the rest of the repo. **`config.test_settings` requires PostgreSQL** via `DATABASE_URL` (local Docker: `docker-compose.test.yml`; CI matches the same settings module). See [README.md](../README.md#running-tests).

```python
# my_skeleton_tracker/tests/test_skeleton_collector.py
"""Customize: expand with mocks for HTTP, rate limits, etc."""

from io import StringIO

import pytest
from django.core.management import call_command

from my_skeleton_tracker.models import SkeletonRun
from my_skeleton_tracker.services import record_skeleton_run


@pytest.mark.django_db
def test_record_skeleton_run_creates_and_increments():
    # Tests the service layer (preferred surface for DB assertions).
    row1, created1 = record_skeleton_run(source_key="alpha")
    assert created1 is True
    assert row1.run_count == 1

    row2, created2 = record_skeleton_run(source_key="alpha")
    assert created2 is False
    assert row2.id == row1.id
    assert row2.run_count == 2


@pytest.mark.django_db
def test_run_my_skeleton_tracker_command_integration():
    # Runs the full command path against the real configured DB backend (Postgres in CI).
    out = StringIO()
    call_command("run_my_skeleton_tracker", "--source-key", "cmd-test", stdout=out)
    row = SkeletonRun.objects.get(source_key="cmd-test")
    assert row.run_count == 1
```

## 5. Configuration and secrets

- Document new environment variables in `.env.example` and any ops doc under `docs/operations/`.
- Use **[operations/github.md](operations/github.md)** for GitHub (tokens via `get_github_token` / `get_github_client`).

## 6. Tests

- Add tests under `<app>/tests/`; keep exit codes and boundaries mockable.
- Run `python -m pytest` locally; CI runs **lint** (pre-commit), **Pyright**, and **test** (pytest with Postgres and coverage); see [README.md](../README.md#running-tests) for local Postgres parity and `uv run pyright` for typing.

## 7. Docs

- Update [Workflow.md](Workflow.md) if execution order or scheduling behavior changes.
- If the new collector writes to workspace or Pinecone, mention paths/namespaces in [Workspace.md](Workspace.md) or the app's service doc.
