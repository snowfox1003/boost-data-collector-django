# Boost Collector Runner

## Overview

This Django app **orchestrates** collector work: it reads a YAML schedule, decides which `manage.py` commands should run for a given trigger (daily, weekly, monthly, interval, or on Boost release), and runs them **in process** via Django’s `call_command`. It does **not** fetch remote data, write to your tracker models, or define collectors—that logic lives in the other apps whose management commands you list in the schedule.

## How this app works

1. **Schedule file**
   The canonical file is [`config/boost_collector_schedule.yaml`](../config/boost_collector_schedule.yaml). You can point elsewhere with the `BOOST_COLLECTOR_SCHEDULE_YAML` setting (see [`schedule_config.py`](schedule_config.py)).

2. **Load and validate**
   [`schedule_config.load_config`](schedule_config.py) reads the YAML and validates structure: each **group** has a `default_time` (UTC `HH:MM`) and a list of **tasks**. Each task has at least `command` (a Django management command name) and `schedule` (`daily`, `weekly`, `monthly`, `on_release`, or `interval`), plus optional `args`, `enabled`, and schedule-specific fields (`on` / `day_of_week`, `on` / `day_of_month`, `minutes` for interval).

3. **Which tasks run**
   [`get_tasks_for_schedule`](schedule_config.py) filters tasks to those matching the current invocation: schedule kind, optional **group** id, weekday for weekly, day for monthly, or interval length. The **`default`** schedule kind is special: it is used for the **group batch** (daily + weekly-for-today + monthly-for-today + optional `on_release` in one run); interval tasks are excluded from that batch and are triggered separately.

4. **`run_scheduled_collectors`**
   The [management command](management/commands/run_scheduled_collectors.py) calls `get_tasks_for_schedule`, then runs each selected task **sequentially** with `call_command(command, *args)`. Exit status is **0** only if every command succeeds (unless `--stop-on-failure` stops early). For `on_release` (and for `default` when release tasks are included), it consults `boost_library_tracker.release_check.has_new_boost_release()`; if there is no new Boost release, `on_release` tasks are skipped.

5. **Celery Beat**
   [`get_beat_schedule`](schedule_config.py) builds `CELERY_BEAT_SCHEDULE` entries: one **crontab** per group at that group’s `default_time` (running the group batch via kwargs `schedule_kind=default` and `group_id=...`), and separate **interval** entries per distinct `minutes` value that invoke the same command with `schedule_kind=interval`. The Celery entry point is [`run_scheduled_collectors_task`](tasks.py), which forwards to `run_scheduled_collectors` with the right CLI flags.

6. **No app-owned data**
   This package has [no models](models.py); it only wires configuration to management commands.

For broader platform context (databases, deployment, other services), see the repo root [README](../README.md) and [docs/Workflow.md](../docs/Workflow.md) where the schedule is documented.

## Common tasks

- Run one schedule group once (smoke test):
  `python manage.py run_scheduled_collectors --schedule daily --group github`
  (more examples in the root [README](../README.md).)
- Change what runs when: edit the YAML schedule and redeploy; keep `command` values aligned with real commands under each app’s `management/commands/`.

## Main command: `run_scheduled_collectors`

Runs tasks from the schedule file for the selected schedule type. Exits with status **0** only when all invoked collectors succeed (see `--stop-on-failure`).

| Option | Description |
| --- | --- |
| `--schedule` | **Required.** `daily` \| `weekly` \| `monthly` \| `on_release` \| `interval` \| `default`. `default` runs the group batch (daily + weekly for today + monthly for today + on_release when applicable); **`default` requires `--group`**. |
| `--day-of-week` | For `weekly`: weekday name (e.g. `monday`). **Required** when `--schedule weekly`. |
| `--day-of-month` | For `monthly`: day 1–31. **Required** when `--schedule monthly`. |
| `--interval-minutes` | For `interval`: repeat every *N* minutes (1–180). **Required** when `--schedule interval`. |
| `--group` | Limit to one YAML group. **Required** with `--schedule default`. For other schedule kinds, omit to run every group. |
| `--stop-on-failure` | Stop after the first failing collector instead of continuing. |

Run `python manage.py run_scheduled_collectors --help` for the full CLI.

## Package

- **Django app label:** `boost_collector_runner`
- **Path (from repo root):** `boost_collector_runner/`
- **Registration:** Listed under `INSTALLED_APPS` in [`config/settings.py`](../config/settings.py).

## Management commands

| Command | Description |
| --- | --- |
| `run_scheduled_collectors` | Run collectors from the YAML schedule for a given schedule type and optional group. |

## Tests

From the repo root (after [README prerequisites](../README.md#running-tests)):

```bash
python -m pytest boost_collector_runner/tests/ -v
```
