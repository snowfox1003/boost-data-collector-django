# How to test the Celery task

This guide explains how to confirm the Celery worker runs **`boost_collector_runner.tasks.run_scheduled_collectors_task`** correctly. Beat schedules one task per YAML group (and interval tasks when configured); you can also queue a group batch once for testing.

---

## Prerequisites

- Python env with project dependencies installed: `pip install -r requirements.txt`
- **Redis** running (Celery uses it as the message broker). Default: `localhost:6379`.

  - **Windows:** Install Redis (e.g. via WSL, or [Redis for Windows](https://github.com/microsoftarchive/redis/releases)), or use Docker: `docker run -d -p 6379:6379 redis`
  - **macOS:** `brew install redis` then `brew services start redis` (or `redis-server`)
  - **Linux:** `sudo apt install redis-server` (or equivalent), then start Redis

---

## Step 1: Start the Celery worker (Terminal 1)

Open a terminal in the project root and run:

```bash
celery -A config worker -l info
```

**Windows:** The project configures the worker to use the `solo` pool on Windows automatically, so you don't get `PermissionError: [WinError 5]`. If you still see that error, run: `celery -A config worker -l info --pool=solo`. CI runs the full pytest suite on **`windows-latest`** (`test-windows` job in [`.github/workflows/actions.yml`](../.github/workflows/actions.yml)).

Leave this running. You should see something like:

```
[config] celery@... ready.
```

This process will **execute** tasks when they are queued (by Beat or when you trigger one manually).

---

## Step 2: Run a scheduled batch once (for testing)

Open a **second** terminal in the project root.

To queue a **daily** batch for one group (example: `github`—must match a `groups:` key in `config/boost_collector_schedule.yaml`):

```bash
python manage.py shell -c "from boost_collector_runner.tasks import run_scheduled_collectors_task; run_scheduled_collectors_task.delay(schedule_kind='daily', group_id='github')"
```

You should see the task run in **Terminal 1** (the worker), for example:

```
Task boost_collector_runner.tasks.run_scheduled_collectors_task[<id>] received
...
run_scheduled_collectors_task: finished successfully
```

The task runs `run_scheduled_collectors` with the same arguments as `python manage.py run_scheduled_collectors`, so command output and errors appear in the worker terminal or in `logs/app.log`.

---

## Optional: Use Celery Beat for the YAML schedule

To run tasks on the schedule defined in `config/boost_collector_schedule.yaml`, start Celery Beat in a **third** terminal:

```bash
celery -A config beat -l info
```

Keep the worker and beat running. Beat queues **`run_scheduled_collectors_task`** per group/time (see [Workflow.md](Workflow.md)).

---

## Summary

| Step | Terminal | Command |
|------|----------|---------|
| 1 | Terminal 1 | `celery -A config worker -l info` (leave running) |
| 2 | Terminal 2 | `python manage.py shell -c "from boost_collector_runner.tasks import run_scheduled_collectors_task; run_scheduled_collectors_task.delay(schedule_kind='daily', group_id='github')"` |
| 3 | Terminal 1 | Watch for task received → succeeded |

If Redis isn't running, the shell command may hang or show a connection error; start Redis first. If the worker isn't running, the task will stay in the queue until a worker is started.
