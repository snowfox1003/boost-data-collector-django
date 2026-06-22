# Concurrency and locking topology

This document maps in-process synchronization primitives across the codebase: what each lock protects, its scope, and acquisition-order constraints. The goal is to make implicit coordination visible so contributors do not introduce deadlocks or data races when modifying concurrent code.

For isolating external SDK state behind explicit types, see [`core/adapters/protocols.py`](../core/adapters/protocols.py) (adapters own SDK handles; concurrency managers own locks).

---

## Topology table

| Name | Location | Protects | Scope | Ordering constraints |
|------|----------|----------|-------|----------------------|
| `_ScrapingTokenRoundRobin._lock` | `core/operations/github_ops/tokens.py` | Lazy `itertools.cycle` and `next()` for scraping tokens | Process-global | Standalone |
| `_BlobUploadLimiter._semaphore` | `core/operations/github_ops/git_ops.py` | Concurrent GitHub blob POSTs during folder upload | Process-global | Standalone |
| `_WorkerSessionStore._thread_local` | `core/operations/github_ops/git_ops.py` | Per-thread `requests.Session` keyed by token | Per-thread | Not a lock; no ordering |
| `_ChannelJoinCoordinator._check_lock` | `core/operations/slack_ops/channels.py` | Skip overlapping background join-check runs (try-acquire only) | Process-global | Standalone |
| `_ChannelJoinCoordinator._stop_event` | same | Signal background join thread to exit | Process-global | Used with `_check_lock`, not nested |
| `_CloneRegistry._lock` | `github_activity_tracker/workspace.py` | Set of clone paths for end-of-run cleanup | Process-global | After per-repo lock when nested (see below) |
| `_RepoLockRegistry._guard` + per-repo locks | `github_activity_tracker/big_commit.py` | Concurrent clone/fetch for same repo | Per (owner, repo) | Before clone registry lock when nested |

---

## Acquisition-order rules

Only one place nests locks within a subsystem. **No cross-module lock nesting** exists.

### GitHub big commits (`github_activity_tracker`)

1. Per-repo lock (`_RepoLockRegistry.lock_for`)
2. Clone registry lock (`_CloneRegistry`) — via `register_clone` inside `ensure_repo_cloned`

`get_registered_clones` and `clear_clone_registry` only touch the clone registry (no repo lock).

---

## Already-encapsulated concurrency (no module-level locks)

| Component | Location | Mechanism |
|-----------|----------|-----------|
| `PineconeIngestion` | `cppa_pinecone_sync/ingestion.py` | `ThreadPoolExecutor` scoped to `update_documents` batches |
| Log handler emit | `config/logging_handlers.py` | Instance `_emit_lock` on handler class |

---

## Contributor guidelines

1. **Do not add bare module-level `threading.Lock()`** — wrap protected state in a private `_XxxState` or `_XxxRegistry` class with a module-level singleton.
2. **Document at definition** — each concurrency manager class needs a docstring stating what it protects and any ordering constraints.
3. **Update this file** when adding or changing locks.
4. **Prefer adapter/protocol patterns** for external SDK state ([`core/adapters/protocols.py`](../core/adapters/protocols.py)); use concurrency managers only for in-process coordination.
