# Core package: stable public surfaces

The `core` Django app holds shared infrastructure. Treat the following as the **supported internal API** for collectors and cross-app helpers. Other modules under `core/` may change without notice; prefer importing from the paths below.

## Collectors

| Import | Purpose |
|--------|---------|
| `core.collectors.CollectorBase` | **Deprecated** (removed in v1.0): legacy abstract `run()`, optional `sync_pinecone()`, `handle_error()` with structured logging. Subclassing emits `DeprecationWarning` at class definition time. Prefer `AbstractCollector`|
| `core.collectors.AbstractCollector` | Preferred contract: `name`, `validate_config()`, `collect()`; concrete `run()` runs validate then collect; same lifecycle hooks as `CollectorBase`. |
| `core.collectors.CollectorRunnable` | `Protocol` for objects returned from `get_collector()` (`run`, `sync_pinecone`, `handle_error`). |
| `core.collectors.BaseCollectorCommand` | Thin `BaseCommand` adapter: runs `get_collector(**opts).run()` then `sync_pinecone()`. |
| `core.collectors.DjangoCommandCollector` | Wraps `call_command(name)` for tests or glue code. |

### Collector base class usage (migration status)

All **application** collectors listed below subclass **`AbstractCollector`** (`name`, `validate_config()`, `collect()`). **`BaseCollectorCommand`** runs `run()` (validate then collect) and `sync_pinecone()` for each.

| Management command | Collector class | Primary module |
|--------|-----------------|----------------|
| `run_boost_usage_tracker` | `BoostUsageTrackerCollector` | `boost_usage_tracker.management.commands.run_boost_usage_tracker` |
| `run_boost_github_activity_tracker` | `BoostGithubActivityCollector` | `boost_library_tracker.management.commands.run_boost_github_activity_tracker` |
| `run_clang_github_tracker` | `ClangGithubTrackerCollector` | `clang_github_tracker.collectors` |
| `run_boost_library_usage_dashboard` | `BoostLibraryUsageDashboardCollector` | `boost_library_usage_dashboard.collectors` |
| `run_boost_library_docs_tracker` | `BoostLibraryDocsTrackerCollector` | `boost_library_docs_tracker.management.commands.run_boost_library_docs_tracker` |
| `run_boost_mailing_list_tracker` | `BoostMailingListTrackerCollector` | `boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker` |
| `run_cppa_user_tracker` | `CppaUserTrackerCollector` | `cppa_user_tracker.management.commands.run_cppa_user_tracker` |
| `run_cppa_pinecone_sync` | `CppaPineconeSyncCollector` | `cppa_pinecone_sync.management.commands.run_cppa_pinecone_sync` |
| `run_cppa_slack_tracker` | `CppaSlackTrackerCollector` | `cppa_slack_tracker.management.commands.run_cppa_slack_tracker` |
| `run_cppa_youtube_script_tracker` | `CppaYoutubeScriptTrackerCollector` | `cppa_youtube_script_tracker.management.commands.run_cppa_youtube_script_tracker` |
| `run_wg21_paper_tracker` | `Wg21PaperTrackerCollector` | `wg21_paper_tracker.collectors` |
| `run_discord_activity_tracker` | `DiscordActivityCollector` | `discord_activity_tracker.management.commands.run_discord_activity_tracker` |
| `backfill_discord_activity_tracker` | `DiscordBackfillCollector` | `discord_activity_tracker.management.commands.backfill_discord_activity_tracker` |

**Still on `CollectorBase` (framework only):** `DjangoCommandCollector` in `core.collectors.base` subclasses the legacy abstract base for `call_command` glue. New app collectors should **not** subclass `CollectorBase`.

## Failure classification

| Import | Purpose |
|--------|---------|
| `core.errors.CollectorFailureCategory` | Enum of coarse failure buckets (`network`, `command`, …). |
| `core.errors.classify_failure(exc)` | Map an exception to `CollectorFailureCategory` for logs and metrics. |

Log records from `CollectorBase.handle_error` / `AbstractCollector.handle_error` include `extra` keys: `collector`, `collector_phase`, `failure_category`.

## Tracker protocols (DTOs)

Structural contracts for **data** that crosses tracker layers (sync outcomes, activity events before ORM persistence, incremental checkpoints). These live in **`core.protocols`** and complement **orchestration** types in `core.collectors` (for example `CollectorRunnable` for management-command phases).

| Import | Purpose |
|--------|---------|
| `core.protocols.TrackerResult` | `@runtime_checkable` protocol: `success`, `counts` (`Mapping[str, int]`). |
| `core.protocols.ActivityRecord` | `@runtime_checkable` protocol: portable activity row (`source_system`, `external_id`, `occurred_at`, …). |
| `core.protocols.IncrementalState` | `@runtime_checkable` protocol: `checkpoint_token`, `human_readable_marker`, `extras`. |
| `core.protocols.require_tracker_result` / `require_activity_record` | Runtime guards raising `TypeError` when an object does not satisfy the protocol. |

Implementations are frozen dataclasses in each tracker app (for example `github_activity_tracker.protocol_impl`, `discord_activity_tracker.protocol_impl`). Prefer dataclasses over plain `dict` for reliable `isinstance` checks with `@runtime_checkable`.

**Local static check:** with dev dependencies installed (`requirements-dev.lock`), from the repo root run **`uv run pyright`** (same as the **`pyright`** job in [`.github/workflows/actions.yml`](../.github/workflows/actions.yml)). Root **`pyrightconfig.json`** scopes analysis to `core`, `github_activity_tracker`, and `discord_activity_tracker` and excludes **`core/pyright_samples/**`** from that run; **`core/tests/test_protocols.py`** still exercises positive/negative protocol assignment snippets via subprocess.

## Reducing coupling

- Prefer **no** `ForeignKey` from one tracker app into another's models (see Development guideline).
- When you need shared behavior, add it under `core` (for example **`core.operations`** for Slack/markdown/file helpers, or **`core.operations.github_ops`** for GitHub API/git/tokens). Those utilities are **not** separate Django apps—they live under the **`core`** package and are not listed in **`INSTALLED_APPS`**.
- Long-term: shrink opportunistic imports between tracker apps by extracting shared protocols into `core` or small neutral apps (see **[Tracker protocols (DTOs)](#tracker-protocols-dtos)** for typed data shapes).
- The current state of all cross-app FKs, ORM read-coupling, and Python imports is catalogued in **[cross-app-dependencies.md](cross-app-dependencies.md)**, together with `import-linter` contracts that can enforce the coupling guideline mechanically.

## Related docs

- [How to add a collector](How_to_add_a_collector.md)
- [Development_guideline.md](Development_guideline.md)
- [cross-app-dependencies.md](cross-app-dependencies.md)
