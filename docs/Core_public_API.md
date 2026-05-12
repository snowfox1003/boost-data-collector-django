# Core package: stable public surfaces

The `core` Django app holds shared infrastructure. Treat the following as the **supported internal API** for collectors and cross-app helpers. Other modules under `core/` may change without notice; prefer importing from the paths below.

## Collectors

| Import | Purpose |
|--------|---------|
| `core.collectors.CollectorBase` | Abstract `run()`, optional `sync_pinecone()`, `handle_error()` with structured logging. |
| `core.collectors.BaseCollectorCommand` | Thin `BaseCommand` adapter: runs `get_collector(**opts).run()` then `sync_pinecone()`. |
| `core.collectors.DjangoCommandCollector` | Wraps `call_command(name)` for tests or glue code. |

## Failure classification

| Import | Purpose |
|--------|---------|
| `core.errors.CollectorFailureCategory` | Enum of coarse failure buckets (`network`, `command`, …). |
| `core.errors.classify_failure(exc)` | Map an exception to `CollectorFailureCategory` for logs and metrics. |

Log records from `CollectorBase.handle_error` include `extra` keys: `collector`, `collector_phase`, `failure_category`.

## Reducing coupling

- Prefer **no** `ForeignKey` from one tracker app into another's models (see Development guideline).
- When you need shared behavior, add it under `core` (for example **`core.operations`** for Slack/markdown/file helpers, or **`core.operations.github_ops`** for GitHub API/git/tokens). Those utilities are **not** separate Django apps—they live under the **`core`** package and are not listed in **`INSTALLED_APPS`**.
- Long-term: shrink opportunistic imports between tracker apps by extracting shared protocols into `core` or small neutral apps.
- The current state of all cross-app FKs, ORM read-coupling, and Python imports is catalogued in **[cross-app-dependencies.md](cross-app-dependencies.md)**, together with `import-linter` contracts that can enforce the coupling guideline mechanically.

## Related docs

- [How to add a collector](How_to_add_a_collector.md)
- [Development_guideline.md](Development_guideline.md)
- [cross-app-dependencies.md](cross-app-dependencies.md)
