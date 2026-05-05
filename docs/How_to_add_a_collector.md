# How to add a collector

This checklist assumes you already have a Django app (or are creating one) with a `management/commands/run_<your_app>.py` entry point. For a high-level diagram and GitHub pipeline notes, see the **Architecture** section in [Development_guideline.md](Development_guideline.md).

## 1. App and command

1. Add the app to `INSTALLED_APPS` in `config/settings.py` if it is new.
2. Implement `management/commands/run_<name>.py` so it exits with status **0** on success and non-zero on failure (so `run_scheduled_collectors` can detect failures).

## 2. Register the command in YAML

Add a task under the right group in [`config/boost_collector_schedule.yaml`](../config/boost_collector_schedule.yaml) (see [Workflow.md](Workflow.md#2-boost-collector-runner-and-yaml-schedule)). Celery Beat runs **`boost_collector_runner.tasks.run_scheduled_collectors_task`** per group and schedule.

## 3. Shared abstractions (recommended)

- Subclass [`CollectorBase`](../core/collectors/base.py) for a common `run()` / `handle_error()` / `sync_pinecone()` contract, and use [`BaseCollectorCommand`](../core/collectors/command_base.py) so the management command stays thin.
- [`DjangoCommandCollector`](../core/collectors/base.py) remains available for tests or internal `call_command` wrappers.

## 4. Configuration and secrets

- Document new environment variables in `.env.example` and any ops doc under `docs/operations/`.
- Use **[operations/github.md](operations/github.md)** for GitHub (tokens via `get_github_token` / `get_github_client`).

## 5. Tests

- Add tests under `<app>/tests/`; keep exit codes and boundaries mockable.
- Run `python -m pytest` locally; CI runs with `DATABASE_URL` pointing at Postgres (see [README.md](../README.md#running-tests) for local Postgres parity).

## 6. Docs

- Update [Workflow.md](Workflow.md) if execution order or scheduling behavior changes.
- If the new collector writes to workspace or Pinecone, mention paths/namespaces in [Workspace.md](Workspace.md) or the app's service doc.
