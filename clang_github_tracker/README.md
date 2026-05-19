# Clang GitHub Tracker

## Overview

Collects **LLVM/Clang GitHub** activity (issues, PRs, commits) for configured repositories, similar in shape to `github_activity_tracker` but scoped to the Clang ecosystem. Uses shared `core.operations.github_ops` patterns.

## Data workflow

`run_clang_github_tracker` mirrors the Boost pipeline at a smaller scope: **GitHub → DB + raw JSON → Markdown → optional git push → optional Pinecone**. `backfill_clang_github_tracker` replays **existing raw JSON** into the Clang tables without calling the network. Service details: [docs/service_api/clang_github_tracker.md](../docs/service_api/clang_github_tracker.md).

### Where we fetch data

**GitHub API** activity for **`llvm/llvm-project`** (and related repos configured for this deployment) via the same client stack as other GitHub collectors. Watermarks come from **PostgreSQL**, not a `state.json` file.

### How data is saved to the database

PostgreSQL rows in this app are **minimal sync state**, not full GitHub payloads. **`ClangGithubIssueItem`** stores one row per issue or PR **number** (plus `is_pull_request`, `github_created_at`, **`github_updated_at`** as the API watermark for the next incremental fetch). **`ClangGithubCommit`** stores one row per **commit SHA** (plus `github_committed_at`). Titles, bodies, labels, and the rest of the API response are **not** duplicated in these tables—they are kept as **raw JSON** under `WORKSPACE_DIR`, using the same `github_activity_tracker` workspace layout as shared tooling expects. **References:** [docs/Schema.md, section 2b — Clang GitHub Tracker](../docs/Schema.md#2b-clang-github-tracker-clang_github_tracker) · [`models.py`](models.py) · [docs/service_api/clang_github_tracker.md](../docs/service_api/clang_github_tracker.md).

### How content is published to GitHub

Markdown is rendered to disk, then [`publisher.py`](publisher.py) can **clone/pull/push** the context repository configured with **`CLANG_GITHUB_CONTEXT_REPO_*`** when `--skip-remote-push` is not set. Requires **`GITHUB_TOKEN_WRITE`** (or configured fallback) for authenticated git operations.

### How vectors sync to Pinecone

Unless `--skip-pinecone` is set, the collector shells out to **`run_cppa_pinecone_sync`** for issues/PRs using the shared GitHub preprocessor path, landing vectors in the configured namespace. See [docs/Pinecone_preprocess_guideline.md](../docs/Pinecone_preprocess_guideline.md).

## Common tasks

- Run the tracker: `python manage.py run_clang_github_tracker --help`.
- Repair or catch-up: `python manage.py backfill_clang_github_tracker --help`.
- Tokens and rate limits: root [README](../README.md#github-tokens) and [docs/operations/github.md](../docs/operations/github.md).

## Main command: `run_clang_github_tracker`

Fetches `llvm/llvm-project` activity into raw JSON + DB; optional Markdown export, remote push, and Pinecone. Resume uses **DB watermarks** (not `state.json`).

| Option | Description |
| --- | --- |
| `--dry-run` | No sync, export, push, or Pinecone; log resolved windows only. |
| `--skip-github-sync` | Skip API fetch / raw + DB upserts. |
| `--skip-markdown-export` | Skip `.md` export from this run’s results. |
| `--skip-remote-push` | Skip push to `CLANG_GITHUB_CONTEXT_REPO_*`. |
| `--skip-pinecone` | Skip `run_cppa_pinecone_sync` for issues/PRs. |
| `--since`, `--from-date`, `--start-time` | Sync window start (`YYYY-MM-DD` or ISO-8601). Aliases are equivalent. |
| `--until`, `--to-date`, `--end-time` | Sync window end; same formats as `--since`. |

### `backfill_clang_github_tracker`

Scans `raw/github_activity_tracker/<owner>/<repo>/commits|issues|prs/*.json` and upserts Clang DB rows. **No CLI options** beyond Django defaults—behavior is fully automatic from the raw tree.

## Management commands

| Command | Purpose |
| --- | --- |
| `run_clang_github_tracker` | Primary GitHub sync for Clang repos. |
| `backfill_clang_github_tracker` | Backfill or repair historical GitHub data. |

Run `python manage.py COMMAND --help` for options.

## Tests

```bash
python -m pytest clang_github_tracker/tests/ -v
```

(from repo root; see root [README](../README.md#running-tests).)
