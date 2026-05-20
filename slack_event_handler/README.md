# Slack Event Handler

## Overview

Django app that runs a **Slack Socket Mode** listener during **`runserver`** so inbound Slack events can be handled in-process. Production-style deployments typically use a different entrypoint; see module docstrings in [`runner.py`](runner.py) and [`apps.py`](apps.py) for startup behavior.

## Data workflow

This app is **event-driven**, not YAML-scheduled like the batch collectors. It reacts to Slack events (for example huddle canvases), writes lightweight **workspace JSON/HTML**, and can upload generated Markdown to GitHub. Per-app service APIs: [docs/service_api/README.md](../docs/service_api/README.md). It **does not** define ORM models for long-term analytics—that work belongs to [`cppa_slack_tracker`](../cppa_slack_tracker/README.md).

### Where we fetch data

**Slack Web API / Socket Mode** events (bot tokens per configured workspace). Huddle flows download private HTML/transcript payloads Slack exposes for a file/canvas id.

### How data is saved to the database

**No Django ORM persistence in this app.** Working state, downloaded JSON, and HTML live under the **workspace** (`slack_event_handler` helpers in [`workspace.py`](workspace.py)). For long-lived Slack rows, see [`cppa_slack_tracker`](../cppa_slack_tracker/README.md) and [docs/Schema.md, section 6 — Slack Activity Tracker](../docs/Schema.md#6-slack-activity-tracker).

### How content is published to GitHub

[`utils/huddle_processor.py`](utils/huddle_processor.py) renders Markdown, then **`core.operations.github_ops.upload_file`** commits it to **`GITHUB_SLACK_HUDDLE_REPO_OWNER` / `GITHUB_SLACK_HUDDLE_REPO_NAME`** (default branch from `GITHUB_DEFAULT_BRANCH`). Requires a token with contents write access to that repository.

### How vectors sync to Pinecone

**Not applicable.** Huddle transcripts are not upserted by this listener; use batch pipelines + [`cppa_pinecone_sync`](../cppa_pinecone_sync/README.md) if Slack text should also live in the vector index. See [docs/Pinecone_preprocess_guideline.md](../docs/Pinecone_preprocess_guideline.md).

## Common tasks

- Local dev with events: `python manage.py runserver` (listener starts in the reloader child only).
- Run the collector-style command directly: `python manage.py run_slack_event_handler --help`.
- Cross-cutting docs: [docs/service_api/README.md](../docs/service_api/README.md) (per-app service API index).

## Main command: `run_slack_event_handler`

Starts the unified **Socket Mode** listener (huddle AI note / transcript tracking and Slack PR-comment bot). Requires Slack app tokens configured in Django settings (see command module and `core.operations.slack_ops`).

| Option | Description |
| --- | --- |
| `--dry-run` | Validate `SLACK_BOT_TOKEN_<id>` / `SLACK_APP_TOKEN_<id>` per configured team; **do not** start the listener. |

## Management commands

| Command | Purpose |
| --- | --- |
| `run_slack_event_handler` | Long-running Slack event handling entrypoint (see module docstring and `--help`). |

Run `python manage.py COMMAND --help` for options.

## Tests

```bash
python -m pytest slack_event_handler/tests/ -v
```

(from repo root; see root [README](../README.md#running-tests) for `DATABASE_URL` and prerequisites.)
