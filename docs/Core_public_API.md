# Core package: stable public surfaces

Stability guarantees for these imports are defined in [STABILITY.md](../STABILITY.md) (Tier A).

The `core` Django app holds shared infrastructure. Treat the following as the **supported internal API** for collectors and cross-app helpers. Other modules under `core/` may change without notice; prefer importing from the paths below.

## Collectors

| Import | Purpose |
|--------|---------|
| `core.collectors.AbstractCollector` | Collector contract: `name`, `validate_config()`, `collect() -> TrackerResult`; concrete `run()` runs validate → `load_incremental_state()` → collect (validates result, backfills `duration_seconds`) → `post_collect()`; optional `sync_pinecone()`, `handle_error()` with structured logging. |
| `core.collectors.CollectorRunnable` | `Protocol` for objects returned from `get_collector()` (`run() -> TrackerResult`, `sync_pinecone`, `handle_error`, `last_result`). |
| `core.collectors.BaseCollectorCommand` | Thin `BaseCommand` adapter: runs `get_collector(**opts).run()`, logs structured `TrackerResult` fields, then `sync_pinecone()`. |
| `core.collectors.GenericTrackerResult` | Default frozen `TrackerResult` DTO (`ok()`, `failed()`); used by stubs and simple collectors. |
| `core.collectors.GenericIncrementalState` | Default frozen `IncrementalState` DTO for checkpoint hooks. |
| `core.collectors.GenericActivityRecord` | Default frozen `ActivityRecord` DTO for portable activity rows. |

### Application collectors

All **application** collectors listed below subclass **`AbstractCollector`** (`name`, `validate_config()`, `collect()`). **`BaseCollectorCommand`** runs `run()` (validate then collect) and `sync_pinecone()` for each.

| Management command | Collector class | Primary module |
|--------|-----------------|----------------|
| `run_boost_usage_tracker` | `BoostUsageTrackerCollector` | `boost_usage_tracker.management.commands.run_boost_usage_tracker` |
| `run_boost_github_activity_tracker` | `BoostGithubActivityCollector` | `boost_library_tracker.management.commands.run_boost_github_activity_tracker` |
| `collect_boost_libraries` | `CollectBoostLibrariesCollector` | `boost_library_tracker.management.commands.collect_boost_libraries` |
| `run_clang_github_tracker` | `ClangGithubTrackerCollector` | `clang_github_tracker.collectors` |
| `run_boost_library_usage_dashboard` | `BoostLibraryUsageDashboardCollector` | `boost_library_usage_dashboard.collectors` |
| `run_boost_library_docs_tracker` | `BoostLibraryDocsTrackerCollector` | `boost_library_docs_tracker.management.commands.run_boost_library_docs_tracker` |
| `run_boost_mailing_list_tracker` | `BoostMailingListTrackerCollector` | `boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker` |
| `run_cppa_user_tracker` | `CppaUserTrackerCollector` | `cppa_user_tracker.management.commands.run_cppa_user_tracker` |
| `run_cppa_pinecone_sync` | `CppaPineconeSyncCollector` | `cppa_pinecone_sync.management.commands.run_cppa_pinecone_sync` |
| `run_cppa_slack_tracker` | `CppaSlackTrackerCollector` | `cppa_slack_tracker.management.commands.run_cppa_slack_tracker` |
| `run_cppa_youtube_script_tracker` | `CppaYoutubeScriptTrackerCollector` | `cppa_youtube_script_tracker.management.commands.run_cppa_youtube_script_tracker` |
| `run_wg21_paper_tracker` | `Wg21PaperTrackerCollector` | `wg21_paper_tracker.collectors` |

## Failure classification

| Import | Purpose |
|--------|---------|
| `core.errors.CollectorFailureCategory` | Enum of coarse failure buckets (`network`, `command`, …). |
| `core.errors.classify_failure(exc)` | Map an exception to `CollectorFailureCategory` for logs and metrics. |
| `core.errors.CollectorValidationError` | Marker base for API-boundary validation errors (subclass in your app; maps to `validation`). |
| `core.errors.AuthenticationError` | Marker base for credential-rejection errors (maps to `auth`). |

Log records from `AbstractCollector.handle_error` include `extra` keys: `collector`, `collector_phase`, `failure_category`.

Third-party SDK exceptions (`requests`, `urllib3`, `httpx`, `discord.py`, `slack_sdk`) are classified in [`core/failure_classifiers.py`](../core/failure_classifiers.py) via `isinstance` against SDK types — not by module path.

## Tracker protocols (DTOs)

Structural contracts for **data** that crosses tracker layers (sync outcomes, activity events before ORM persistence, incremental checkpoints). These live in **`core.protocols`** and complement **orchestration** types in `core.collectors` (for example `CollectorRunnable` for management-command phases).

| Import | Purpose |
|--------|---------|
| `core.protocols.TrackerResult` | `@runtime_checkable` protocol: `success`, `counts` (`Mapping[str, int]`), `errors` (`Sequence[str]`), `duration_seconds` (`float \| None`). |
| `core.protocols.ActivityRecord` | `@runtime_checkable` protocol: portable activity row (`source_system`, `external_id`, `occurred_at`, …). |
| `core.activity_types` | Typed `ActivityRecord` fields: `SourceSystem`, `ActivityType`, `ActorExternalId`, UTC `occurred_at` helpers, and `migrate_legacy_activity_fields` / `activity_record_to_legacy_dict` for string payloads. |
| `core.protocols.IncrementalState` | `@runtime_checkable` protocol: `checkpoint_token`, `human_readable_marker`, `extras`. |
| `core.protocols.require_tracker_result` / `require_activity_record` / `require_incremental_state` | Runtime guards raising `TypeError` when an object does not satisfy the protocol. |

Implementations are frozen dataclasses in each tracker app's `protocol_impl.py` (for example `github_activity_tracker.protocol_impl`, `boost_library_tracker.protocol_impl`). They subclass shared bases in **`core.protocol_dto`** (`TrackerResultDataclass`, `IncrementalStateDataclass`, `ActivityRecordDataclass`) which provide canonical `asdict()`, `to_json()`, `from_dict()`, and log-friendly `__repr__`. Simple collectors may return `GenericTrackerResult` directly. Prefer dataclasses over plain `dict` for reliable `isinstance` checks with `@runtime_checkable`.

`BaseCollectorCommand` structured logs include `result_repr` and `result_json` in `extra` when the collector returns a `TrackerResultDataclass` subclass.

`AbstractCollector.collect()` must return a `TrackerResult`. Override `load_incremental_state()` / `persist_incremental_state()` when a collector needs checkpoint read/write between runs (default hooks are no-ops).

**Local static check:** with dev dependencies installed (`requirements-dev.lock`), from the repo root run **`uv run pyright`** (same as the **`pyright`** job in [`.github/workflows/actions.yml`](../.github/workflows/actions.yml)). Root **`pyrightconfig.json`** scopes analysis to `core`, `github_activity_tracker`, `cppa_slack_tracker`, `cppa_user_tracker`, and `cppa_pinecone_sync`, and excludes **`core/pyright_samples/**`** from that run; **`core/tests/test_protocols.py`** still exercises positive/negative protocol assignment snippets via subprocess.

## External adapters

Stable protocols and thin wrappers for vendor SDKs and HTTP clients. Import from **`core.adapters`** (curated `__all__`).

| Import | Purpose |
|--------|---------|
| `core.adapters.PineconeClientProtocol` | Pinecone control-plane + index handle factory (used by `cppa_pinecone_sync` ingestion). |
| `core.adapters.PineconeIndexProtocol` | Vector upsert, metadata update, delete, and stats on one index. |
| `core.adapters.PineconeAdapter` | Production Pinecone SDK wrapper; `PineconeAdapter.from_api_key(api_key)`. |
| `core.adapters.ensure_pinecone_available` | Raise `ImportError` when the `pinecone` package is missing. |
| `core.adapters.SlackWebApiProtocol` | Slack Web API methods used by collectors (`conversations.*`, `users.*`, etc.). |
| `core.adapters.SlackWebApiAdapter` | Default Slack adapter; delegates to `core.operations.slack_ops.client.SlackAPIClient`. |
| `core.adapters.GitHubApiProtocol` | GitHub REST/GraphQL methods used by `github_activity_tracker` and consumers. |
| `core.adapters.GitHubApiAdapter` | Default GitHub adapter; delegates to `core.operations.github_ops.client.GitHubAPIClient`. |

The **`pinecone`** package is imported only from [`core/adapters/pinecone.py`](../core/adapters/pinecone.py). See [core/adapters/README.md](../core/adapters/README.md).

## Reducing coupling

- Prefer **no** `ForeignKey` from one tracker app into another's models (see Development guideline).
- When you need shared behavior, add it under `core` (for example **`core.operations`** for Slack/markdown/file helpers, or **`core.operations.github_ops`** for GitHub API/git/tokens). Those utilities are **not** separate Django apps—they live under the **`core`** package and are not listed in **`INSTALLED_APPS`**.
- Long-term: shrink opportunistic imports between tracker apps by extracting shared protocols into `core` or small neutral apps (see **[Tracker protocols (DTOs)](#tracker-protocols-dtos)** for typed data shapes).
- The current state of all cross-app FKs, ORM read-coupling, and Python imports is catalogued in **[cross-app-dependencies.md](cross-app-dependencies.md)**, together with `import-linter` contracts that can enforce the coupling guideline mechanically.

## Related docs

- [How to add a collector](How_to_add_a_collector.md)
- [Development_guideline.md](Development_guideline.md)
- [cross-app-dependencies.md](cross-app-dependencies.md)
