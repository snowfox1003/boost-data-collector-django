# ADR: Unify batch and event-driven collection paradigms

**Date:** 2026-06-02
**Updated:** 2026-06-18 — This public repository is batch collectors only.

## Context

Boost Data Collector originally ran two collection paradigms in one Django project:

1. **Batch (scheduled) collectors** — YAML-driven schedules executed by Celery Beat → `run_scheduled_collectors_task` → `run_scheduled_collectors`, which invokes `run_*` management commands sequentially within each group batch.
2. **Event-driven (real-time) services** — long-running Socket Mode listeners and similar processes that react to external events as they arrive.

**Current state (public repo):** This repository contains **batch collectors only**. Real-time listeners and related long-running entrypoints are not part of this tree.

Production scheduling for the public repo is defined in [`config/boost_collector_schedule.yaml`](../../config/boost_collector_schedule.yaml). See [Architecture_overview.md](../Architecture_overview.md) for the current app inventory.

Cross-app coupling—especially Foreign Keys into [`cppa_user_tracker`](../cross-app-dependencies.md) as the identity hub—makes module boundaries expensive to move. The sequential batch model remains the primary paradigm **in this repo**.

For system context, see [Architecture overview](../Architecture_overview.md), [Architecture data flow](../Architecture_data_flow.md), [Workflow](../Workflow.md), and [Cross-app dependencies](../cross-app-dependencies.md).

## Decision drivers

- **Correctness** — Batch collectors must not assume global sequential guarantees across Celery groups.
- **Operability** — Operators need to know which process runs batch work vs optional realtime listeners.
- **Maintainability** — Cross-app FKs and import-linter contracts favor incremental separation over a big-bang split.

## Paradigm definitions

### Batch (scheduled) paradigm — **in this repo**

- **Trigger:** Celery Beat entries built from [`boost_collector_runner/schedule_config.py`](../../boost_collector_runner/schedule_config.py) reading the YAML schedule.
- **Entry point:** [`run_scheduled_collectors_task`](../../boost_collector_runner/tasks.py) → [`run_scheduled_collectors`](../../boost_collector_runner/management/commands/run_scheduled_collectors.py).
- **Execution model:** Within one batch, commands run **one after another**. **Different YAML groups** get **separate Beat entries** and may run **in parallel** on different Celery workers.
- **State:** PostgreSQL via each app’s `services.py`; optional files under `workspace/<app>/`.

### Event-driven (real-time) paradigm — **out of scope for this repo**

Long-running Socket Mode listeners and similar services are **not maintained in this public repository**. When such collectors are deployed alongside BDC, run them in a **dedicated process** separate from Celery batch workers.

## App classification (public repo)

| Paradigm | Examples in this repo |
|----------|----------------------|
| **Batch collector** | `github_activity_tracker`, `cppa_slack_tracker`, `boost_mailing_list_tracker`, … |
| **Batch orchestration** | `boost_collector_runner` |
| **Platform** | `core`, `cppa_user_tracker` |

## Decision

Keep **batch collectors in this public repo**. Stay in **one database** until operational swim lanes prove insufficient.

## Migration path (historical)

Phases 1–2 in the original ADR (Compose service for realtime Slack listeners, queue locking fixes) applied to collectors that are no longer in this tree.

## References

- [Workflow.md](../Workflow.md) — batch execution order and Celery Beat behavior
- [boost_collector_runner/README.md](../../boost_collector_runner/README.md)
- [Architecture_data_flow.md](../Architecture_data_flow.md)
